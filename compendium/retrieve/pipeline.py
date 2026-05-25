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
import time
from dataclasses import dataclass, field
from typing import Any

from compendium.config import load_config
from compendium.index.embedder import Embedder, get_embedder
from compendium.retrieve import search
from compendium.retrieve.clients import async_opensearch_client, async_qdrant_client
from compendium.retrieve.coverage import coverage_score
from compendium.retrieve.fusion import FusedHit, reciprocal_rank_fusion

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
    """(rrf_k, page_coverage_threshold, top_k) from config, with defaults."""
    retrieval = load_config().settings.get("retrieval", {})
    rrf_k = int(retrieval.get("rrf_k", 60))
    threshold = float(retrieval.get("page_coverage_threshold", 0.5))
    top_k = int(retrieval.get("top_k", 7))
    return rrf_k, threshold, top_k


def _embedding_model_name() -> str:
    """The model label recorded in the trace."""
    if os.environ.get("COMPENDIUM_EMBED_STUB"):
        return "stub"
    return load_config().embeddings_model


def _page_result(fused: FusedHit) -> PageResult:
    f = fused.fields
    return PageResult(
        entity_id=fused.entity_id,
        title=f.get("title", ""),
        slug=f.get("slug", ""),
        kind=f.get("kind", ""),
        status=f.get("status", ""),
        score=fused.score,
        ranks=dict(fused.ranks),
    )


def _chunk_citation(fused: FusedHit) -> ChunkCitation:
    f = fused.fields
    preview = f.get("body") or f.get("body_preview") or ""
    return ChunkCitation(
        entity_id=fused.entity_id,
        source_title=f.get("source_title"),
        position=f.get("position"),
        score=fused.score,
        preview=" ".join(preview.split())[:200],
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
) -> RetrievalResult:
    """Run the page-first pipeline. Clients/embedder are injectable for tests."""
    rrf_k, threshold, top_k = _retrieval_params()
    embedder = embedder or get_embedder()

    owns_clients = os_client is None and qd_client is None
    os_client = os_client or async_opensearch_client()
    qd_client = qd_client or async_qdrant_client()

    latencies: dict[str, float] = {}
    try:
        # Embed once; reuse the vector for the dense searches and the trace.
        t = time.perf_counter()
        query_vector = embedder.embed([query_text])[0]
        latencies["embed"] = (time.perf_counter() - t) * 1000

        # Fan out to the two pages indexes in parallel.
        t = time.perf_counter()
        os_pages, qd_pages = await asyncio.gather(
            search.opensearch_pages(os_client, query_text, CANDIDATE_POOL_SIZE),
            search.qdrant_pages(qd_client, query_vector, CANDIDATE_POOL_SIZE),
        )
        latencies["pages_fanout"] = (time.perf_counter() - t) * 1000

        fused_pages = reciprocal_rank_fusion(
            {"opensearch": os_pages, "qdrant": qd_pages}, rrf_k=rrf_k
        )
        coverage = coverage_score([f.score for f in fused_pages], top_k)
        pages = [_page_result(f) for f in fused_pages[:top_k]]

        fallback = coverage < threshold
        citations: list[ChunkCitation] = []
        gaps: list[dict[str, Any]] = []
        os_chunks: list[search.Hit] = []
        qd_chunks: list[search.Hit] = []
        fused_chunks: list[FusedHit] = []

        if fallback:
            t = time.perf_counter()
            os_chunks, qd_chunks = await asyncio.gather(
                search.opensearch_chunks(os_client, query_text, CANDIDATE_POOL_SIZE),
                search.qdrant_chunks(qd_client, query_vector, CANDIDATE_POOL_SIZE),
            )
            latencies["chunks_fanout"] = (time.perf_counter() - t) * 1000
            fused_chunks = reciprocal_rank_fusion(
                {"opensearch": os_chunks, "qdrant": qd_chunks}, rrf_k=rrf_k
            )
            citations = [_chunk_citation(f) for f in fused_chunks[:top_k]]
            gaps = [
                {
                    "kind": "low_coverage",
                    "query": query_text,
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
        "query_text": query_text,
        "embedding_model": _embedding_model_name(),
        "query_embedding": query_vector,
        "pipeline": {
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
        "graph_expansion": None,
    }

    return RetrievalResult(
        query_text=query_text,
        pages=pages,
        coverage_score=coverage,
        fallback_to_chunks=fallback,
        citations=citations,
        gaps=gaps,
        trace=trace,
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
        t = result.trace
        repository.insert_query_trace(
            conn,
            query_text=t["query_text"],
            embedding_model=t["embedding_model"],
            query_embedding=t["query_embedding"],
            pipeline=t["pipeline"],
            final_ranking=t["final_ranking"],
            latencies_ms=t["latencies_ms"],
            coverage_score=t["coverage_score"],
            fallback_to_chunks=t["fallback_to_chunks"],
            gaps=t["gaps"],
            corpus_revision=t["corpus_revision"],
            graph_expansion=t["graph_expansion"],
        )
    return result
