"""Phase 5 page-first retrieval tests.

Unit tests (fusion, coverage, the pipeline with injected fake clients) run
anywhere. Integration tests need a migrated ``compendium_test`` database, a
running OpenSearch and Qdrant, and seeded fixtures; they skip if any store is
unreachable and always use the deterministic stub embedder.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.retrieve import pipeline
from compendium.retrieve.coverage import coverage_score
from compendium.retrieve.fusion import reciprocal_rank_fusion
from compendium.retrieve.search import Hit

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit: fusion ----------------------------------------------------------


def test_rrf_candidate_in_both_lists_outranks_one_list():
    os_hits = [Hit("A", 9.0), Hit("B", 8.0)]
    qd_hits = [Hit("A", 0.9)]  # A in both, B in one
    fused = reciprocal_rank_fusion({"o": os_hits, "q": qd_hits})
    assert fused[0].entity_id == "A"
    assert fused[0].score > fused[1].score
    assert fused[0].ranks == {"o": 1, "q": 1}


def test_rrf_is_deterministic():
    lists = {
        "o": [Hit("A", 9.0), Hit("B", 8.0), Hit("C", 1.0)],
        "q": [Hit("C", 0.9), Hit("A", 0.8)],
    }
    first = [(f.entity_id, f.score) for f in reciprocal_rank_fusion(lists)]
    second = [(f.entity_id, f.score) for f in reciprocal_rank_fusion(lists)]
    assert first == second


def test_rrf_single_list_candidate_still_scores():
    fused = reciprocal_rank_fusion({"o": [Hit("solo", 5.0)]})
    assert len(fused) == 1 and fused[0].score > 0


# --- unit: coverage --------------------------------------------------------


def test_coverage_empty_is_zero():
    assert coverage_score([], 7) == 0.0


def test_coverage_single_and_all_equal_are_full():
    assert coverage_score([5.0], 7) == 1.0
    assert coverage_score([3.0, 3.0, 3.0], 7) == 1.0


def test_coverage_is_bounded_and_matches_hand_calc():
    # scores 10,8,2,1 -> normalized 1, .777..., .111..., 0; mean of top 2 = .888...
    cov = coverage_score([10, 8, 2, 1], 2)
    assert 0.0 <= cov <= 1.0
    assert cov == pytest.approx((1.0 + (7 / 9)) / 2)


# --- unit: pipeline with fake clients --------------------------------------


class _FakeOpenSearch:
    def __init__(self, pages, chunks):
        self._pages, self._chunks = pages, chunks

    async def search(self, index, body):
        hits = self._pages if index == "pages" else self._chunks
        return {"hits": {"hits": hits}}

    async def close(self):
        pass


class _FakePoint:
    def __init__(self, id_, score, payload):
        self.id, self.score, self.payload = id_, score, payload


class _FakeQdrant:
    def __init__(self, pages, chunks):
        self._pages, self._chunks = pages, chunks

    async def query_points(
        self, collection_name, query, limit, with_payload,
        query_filter=None, search_params=None,
    ):
        pts = self._pages if collection_name == "pages" else self._chunks
        return SimpleNamespace(points=pts)

    async def close(self):
        pass


def _os_page(id_, score, title):
    return {
        "_id": id_,
        "_score": score,
        "_source": {"title": title, "slug": id_.lower(), "kind": "concept", "status": "canonical"},
    }


def _run(query_text, os_client, qd_client):
    return asyncio.run(
        pipeline.run(query_text, embedder=_StubEmbedder(), os_client=os_client, qd_client=qd_client)
    )


class _StubEmbedder:
    def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


def test_pipeline_covered_query_returns_pages_no_fallback():
    os_pages = [_os_page("A", 9, "Alpha"), _os_page("B", 7, "Beta")]
    qd_pages = [_FakePoint("A", 0.9, {"title": "Alpha", "slug": "a", "kind": "concept", "status": "canonical"}),
                _FakePoint("B", 0.8, {"title": "Beta", "slug": "b", "kind": "concept", "status": "canonical"})]
    result = _run("alpha beta", _FakeOpenSearch(os_pages, []), _FakeQdrant(qd_pages, []))
    assert [p.title for p in result.pages] == ["Alpha", "Beta"]
    assert result.coverage_score >= 0.5
    assert result.fallback_to_chunks is False
    assert result.gaps == []
    # Trace carries every query_traces column; graph_expansion stays null.
    for key in ("pipeline", "final_ranking", "latencies_ms", "query_embedding"):
        assert key in result.trace
    assert len(result.trace["query_embedding"]) == 1024
    assert result.trace["graph_expansion"] is None


def test_pipeline_uncovered_query_falls_back_and_flags_gap():
    # A spread of weakly-separated pages keeps the top-k normalized mean below 0.5.
    os_pages = [_os_page(str(i), 10 - i * 3, f"P{i}") for i in range(5)]
    os_chunks = [{"_id": "c1", "_score": 5, "_source": {"source_title": "Src", "position": 2, "body": "chunk body"}}]
    qd_chunks = [_FakePoint("c1", 0.7, {"position": 2, "body_preview": "chunk body"})]
    result = _run("weakly covered", _FakeOpenSearch(os_pages, os_chunks), _FakeQdrant([], qd_chunks))
    assert result.coverage_score < 0.5
    assert result.fallback_to_chunks is True
    assert result.citations and result.citations[0].entity_id == "c1"
    assert result.gaps and result.gaps[0]["kind"] == "low_coverage"


# --- integration -----------------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


def _make_corpus(monkeypatch, tmp_path) -> tuple[str, str]:
    """Migrate a fresh compendium_test DB, ingest the sample fixture (ingestion
    also generates the source page), and populate both indexes. Returns
    (test_url, admin_url). Skips if any store is unreachable."""
    from compendium.index.clients import (
        opensearch_client,
        opensearch_reachable,
        qdrant_client,
        qdrant_reachable,
    )

    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    if not opensearch_reachable(opensearch_client()):
        pytest.skip("OpenSearch unreachable")
    if not qdrant_reachable(qdrant_client()):
        pytest.skip("Qdrant unreachable")

    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")

    vault = tmp_path / "vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True)

    monkeypatch.setenv("POSTGRES_URL", test_url)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("COMPENDIUM_EMBED_STUB", "1")

    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")  # also writes the source page
    reindex("all")
    return test_url, admin_url


@pytest.fixture
def seeded_corpus(monkeypatch, tmp_path):
    """A source plus its source page, both indexes populated."""
    test_url, admin_url = _make_corpus(monkeypatch, tmp_path)
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


@pytest.fixture
def chunks_only_corpus(monkeypatch, tmp_path):
    """Chunks indexed but the pages indexes emptied: the genuine 'gap' state —
    the source's chunks exist but no page is retrievable yet, so page search
    finds nothing and the pipeline must fall back to chunks."""
    test_url, admin_url = _make_corpus(monkeypatch, tmp_path)
    from compendium.index import opensearch, qdrant
    from compendium.index.clients import opensearch_client, qdrant_client

    opensearch.recreate_index(opensearch_client(), opensearch.PAGES_INDEX)
    qdrant.recreate_collection(qdrant_client(), qdrant.PAGES_COLLECTION)
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def test_covered_query_returns_expected_page_and_traces(seeded_corpus):
    # The seeded corpus has one source page; a lexical match returns it.
    result = pipeline.query("psychological safety team learning")
    assert result.pages, "expected the source page for a covered query"
    assert result.pages[0].title == "Sample Markdown Source"
    assert result.pages[0].kind == "source"
    assert result.fallback_to_chunks is False

    # The trace was persisted with the full pipeline state.
    with psycopg.connect(seeded_corpus) as conn:
        row = conn.execute(
            "SELECT query_text, final_ranking, pipeline, latencies_ms, "
            "coverage_score, query_embedding, graph_expansion "
            "FROM query_traces ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row[0] == "psychological safety team learning"
    assert row[1] and row[2] and row[3]  # final_ranking, pipeline, latencies present
    assert row[4] is not None  # coverage_score
    assert len(row[5]) == 1024  # REAL[] embedding persisted
    assert row[6] is None  # graph_expansion null in Phase 5


def test_uncovered_query_flags_gap_in_trace(chunks_only_corpus):
    # No wiki page exists, so page retrieval is empty -> coverage 0 -> fallback.
    result = pipeline.query("psychological safety team learning")
    assert result.pages == []
    assert result.fallback_to_chunks is True
    assert result.citations, "fallback should attach chunk citations"

    with psycopg.connect(chunks_only_corpus) as conn:
        row = conn.execute(
            "SELECT fallback_to_chunks, gaps, coverage_score FROM query_traces "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row[0] is True  # fallback_to_chunks
    assert len(row[1]) >= 1 and row[1][0]["kind"] == "low_coverage"  # gaps
    assert row[2] == 0.0  # coverage_score


def test_concurrent_page_fanout(seeded_corpus):
    """The two page searches are dispatched together, not sequentially."""
    import compendium.retrieve.search as search_mod

    order: list[str] = []
    real_os, real_qd = search_mod.opensearch_pages, search_mod.qdrant_pages

    async def traced_os(client, q, size):
        order.append("os_start")
        await asyncio.sleep(0.05)
        order.append("os_end")
        return await real_os(client, q, size)

    async def traced_qd(client, v, size):
        order.append("qd_start")
        await asyncio.sleep(0.05)
        order.append("qd_end")
        return await real_qd(client, v, size)

    search_mod.opensearch_pages = traced_os
    search_mod.qdrant_pages = traced_qd
    try:
        pipeline.query("psychological safety")
    finally:
        search_mod.opensearch_pages, search_mod.qdrant_pages = real_os, real_qd

    # Both start before either ends -> concurrent, not sequential.
    assert order[:2] == ["os_start", "qd_start"] or order[:2] == ["qd_start", "os_start"]
