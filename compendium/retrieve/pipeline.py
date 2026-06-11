"""The page-first retrieval pipeline (ADR-003).

Orchestrates: embed the query, fan out to the OpenSearch and Qdrant ``pages``
indexes in parallel, fuse with RRF, score coverage; if coverage is below the
threshold, also fan out to the ``chunks`` indexes, fuse, and attach citations,
flagging the gap. Returns a ``RetrievalResult`` carrying the ranked pages plus
the fully assembled trace payload (persisted by the caller, Phase 5d).

The fan-out is async (``asyncio.gather``); embedding and the eventual trace
write are synchronous. ``run()`` is the async entry for in-loop callers (the
Phase 8 TUI); ``query()`` is the synchronous wrapper for the CLI.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from compendium import config_sections
from compendium.config import load_config
from compendium.index.embedder import Embedder, get_embedder
from compendium.profiling import timed
from compendium.retrieve import search
from compendium.retrieve.clients import async_opensearch_client, async_qdrant_client
from compendium.retrieve.coverage import coverage_score
from compendium.retrieve.fusion import FusedHit, reciprocal_rank_fusion
from compendium.retrieve.normalize import AliasIndex, normalize_query

# Candidate pool fetched from each store before fusion. Larger than top_k so
# fusion has material to work with; the final ranking is trimmed to top_k.
CANDIDATE_POOL_SIZE = 50


@dataclass
class PageResult:
    """One ranked page in the result."""

    entity_id: str
    title: str
    slug: str
    kind: str
    status: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)


@dataclass
class ChunkCitation:
    """One chunk citation attached on fallback."""

    entity_id: str
    source_title: str | None
    position: int | None
    score: float
    preview: str


@dataclass
class RetrievalResult:
    """The pipeline output: ranked pages, coverage, fallback citations, trace."""

    query_text: str
    pages: list[PageResult]
    coverage_score: float
    fallback_to_chunks: bool
    citations: list[ChunkCitation]
    gaps: list[dict[str, Any]]
    trace: dict[str, Any]


def _retrieval_params() -> tuple[int, float, int]:
    """(rrf_k, page_coverage_threshold, top_k) from the retrieval section reader."""
    r = config_sections.retrieval()
    return r["rrf_k"], r["page_coverage_threshold"], r["top_k"]


def _expansion_params() -> dict[str, Any]:
    """Graph-expansion config (ADR-009 fast loop) from the section reader."""
    return config_sections.expansion()


def _embedding_model_name() -> str:
    """The model label recorded in the trace."""
    from compendium.model_clients import use_stub

    if use_stub("embedder"):
        return "stub"
    return load_config().embeddings_model


def _page_result(fused: FusedHit) -> PageResult:
    return PageResult(
        entity_id=fused.entity_id,
        title=fused.title,
        slug=fused.slug,
        kind=fused.kind,
        status=fused.status,
        score=fused.score,
        ranks=dict(fused.ranks),
    )


def _chunk_citation(fused: FusedHit) -> ChunkCitation:
    return ChunkCitation(
        entity_id=fused.entity_id,
        source_title=fused.source_title,
        position=fused.position,
        score=fused.score,
        preview=" ".join(fused.preview.split())[:200],
    )


def _stage_candidates(hits: list[search.Hit]) -> list[dict[str, Any]]:
    return [{"entity_id": h.entity_id, "score": h.score} for h in hits]


def _fused_candidates(fused: list[FusedHit]) -> list[dict[str, Any]]:
    return [
        {"entity_id": f.entity_id, "score": f.score, "ranks": f.ranks} for f in fused
    ]


async def run(
    query_text: str,
    *,
    embedder: Embedder | None = None,
    os_client: Any | None = None,
    qd_client: Any | None = None,
    corpus_revision: str | None = None,
    alias_index: AliasIndex | None = None,
) -> RetrievalResult:
    """Run the page-first pipeline. Clients/embedder are injectable for tests."""
    rrf_k, threshold, top_k = _retrieval_params()
    embedder = embedder or get_embedder()

    # v0.2 Phase 5: rule-based normalization runs before fan-out.
    # Lowercase → strip stop-words → alias expansion. The fan-out and the
    # embedding use the normalized text; the raw text is preserved on the
    # trace's `query_text` field for replay and history.
    raw_query = query_text
    normalized = normalize_query(query_text, alias_index)
    query_text = normalized or raw_query

    owns_clients = os_client is None and qd_client is None
    os_client = os_client or async_opensearch_client()
    qd_client = qd_client or async_qdrant_client()

    latencies: dict[str, float] = {}
    try:
        # Embed once; reuse the vector for the dense searches and the trace.
        with timed("embed", sink=latencies):
            query_vector = embedder.embed([query_text])[0]

        # Fan out to the two pages indexes in parallel.
        with timed("pages_fanout", sink=latencies):
            os_pages, qd_pages = await asyncio.gather(
                search.opensearch_pages(os_client, query_text, CANDIDATE_POOL_SIZE),
                search.qdrant_pages(qd_client, query_vector, CANDIDATE_POOL_SIZE),
            )

        fused_pages = reciprocal_rank_fusion(
            {"opensearch": os_pages, "qdrant": qd_pages}, rrf_k=rrf_k
        )
        coverage = coverage_score([f.score for f in fused_pages], top_k)
        pages = [_page_result(f) for f in fused_pages[:top_k]]

        # Fast-loop graph expansion (ADR-009): walk semantic edges from the top
        # seeds and merge reached pages. No-op when disabled / no edges / graph
        # down, leaving the base ranking and a null graph_expansion.
        graph_expansion_payload: dict[str, Any] | None = None
        exp = _expansion_params()
        if exp["enabled"] and fused_pages:
            from compendium.retrieve import expansion

            seed_scores = {f.entity_id: f.score for f in fused_pages[: exp["seed_k"]]}
            with timed("expansion", sink=latencies):
                outcome = await asyncio.to_thread(
                    expansion.expand, seed_scores,
                    max_hops=exp["max_hops"], decay=exp["decay"], weight=exp["weight"],
                )
            if outcome.reached:
                present = {p.entity_id for p in pages}
                extra = [
                    PageResult(
                        entity_id=r["entity_id"], title=r["title"], slug=r["slug"],
                        kind=r["kind"], status="", score=r["score"],
                        ranks={"expansion_hop": r["hop"]},
                    )
                    for r in outcome.reached if r["entity_id"] not in present
                ]
                if extra:
                    pages = sorted(pages + extra, key=lambda p: -p.score)[:top_k]
                graph_expansion_payload = outcome.payload

        fallback = coverage < threshold
        citations: list[ChunkCitation] = []
        gaps: list[dict[str, Any]] = []
        os_chunks: list[search.Hit] = []
        qd_chunks: list[search.Hit] = []
        fused_chunks: list[FusedHit] = []

        if fallback:
            with timed("chunks_fanout", sink=latencies):
                os_chunks, qd_chunks = await asyncio.gather(
                    search.opensearch_chunks(os_client, query_text, CANDIDATE_POOL_SIZE),
                    search.qdrant_chunks(qd_client, query_vector, CANDIDATE_POOL_SIZE),
                )
            fused_chunks = reciprocal_rank_fusion(
                {"opensearch": os_chunks, "qdrant": qd_chunks}, rrf_k=rrf_k
            )
            citations = [_chunk_citation(f) for f in fused_chunks[:top_k]]
            gaps = [
                {
                    "kind": "low_coverage",
                    "query": raw_query,
                    "coverage_score": coverage,
                    "threshold": threshold,
                }
            ]
    finally:
        if owns_clients:
            await os_client.close()
            await qd_client.close()

    latencies["total"] = sum(
        v for k, v in latencies.items() if k in ("embed", "pages_fanout", "chunks_fanout")
    )

    final_ranking = [
        {
            "entity_id": p.entity_id,
            "title": p.title,
            "slug": p.slug,
            "score": p.score,
            "ranks": p.ranks,
        }
        for p in pages
    ]
    trace = {
        "corpus_revision": corpus_revision,
        # The trace preserves the raw user input for replay / history; the
        # normalized form rides in `pipeline.normalized_query` for v0.2
        # Phase 5 (Shape D part 1, rule-based normalization).
        "query_text": raw_query,
        "embedding_model": _embedding_model_name(),
        "query_embedding": query_vector,
        "pipeline": {
            "normalized_query": query_text,
            "opensearch_pages": _stage_candidates(os_pages),
            "qdrant_pages": _stage_candidates(qd_pages),
            "fused_pages": _fused_candidates(fused_pages),
            "opensearch_chunks": _stage_candidates(os_chunks),
            "qdrant_chunks": _stage_candidates(qd_chunks),
            "fused_chunks": _fused_candidates(fused_chunks),
        },
        "final_ranking": final_ranking,
        "latencies_ms": latencies,
        "coverage_score": coverage,
        "fallback_to_chunks": fallback,
        "gaps": gaps,
        "graph_expansion": graph_expansion_payload,
    }

    return RetrievalResult(
        query_text=raw_query,
        pages=pages,
        coverage_score=coverage,
        fallback_to_chunks=fallback,
        citations=citations,
        gaps=gaps,
        trace=trace,
    )


def persist_query_trace(conn: Any, trace: dict[str, Any]) -> Any:
    """Write one ``query_traces`` row from a result's trace payload; return its id.

    Shared by ``query()`` and the v0.2 Phase 6 ``ask`` composer so both persist
    the retrieval trace identically and the ask trace can reference its id.
    """
    from compendium.db import repository

    return repository.insert_query_trace(
        conn,
        query_text=trace["query_text"],
        embedding_model=trace["embedding_model"],
        query_embedding=trace["query_embedding"],
        pipeline=trace["pipeline"],
        final_ranking=trace["final_ranking"],
        latencies_ms=trace["latencies_ms"],
        coverage_score=trace["coverage_score"],
        fallback_to_chunks=trace["fallback_to_chunks"],
        gaps=trace["gaps"],
        corpus_revision=trace["corpus_revision"],
        graph_expansion=trace["graph_expansion"],
    )


def query(
    query_text: str, *, persist: bool = True, **kwargs: Any
) -> RetrievalResult:
    """Synchronous wrapper over ``run`` for the CLI.

    When ``persist`` is true (the default), resolve the corpus revision and
    write exactly one ``query_traces`` row, regardless of outcome. Unit tests
    that inject fake clients pass ``persist=False`` to stay off the database.
    """
    if not persist:
        return asyncio.run(run(query_text, **kwargs))

    from compendium.db import repository
    from compendium.db.connection import connection

    with connection() as conn:
        corpus_revision = repository.ensure_corpus_revision(conn)
        result = asyncio.run(run(query_text, corpus_revision=corpus_revision, **kwargs))
        persist_query_trace(conn, result.trace)
    return result
