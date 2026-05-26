"""Phase 9 curation-loop tests.

Unit tests (expansion scoring) run anywhere. Integration tests need a migrated
``compendium_test`` DB plus OpenSearch, Qdrant, and Memgraph; they skip if a
store is unreachable and use the deterministic synth/embed stubs. The acceptance
test exercises the full ADR-009 loop: gap -> signal -> synth -> promote -> the
replay of the original query improves.
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
from compendium.retrieve.expansion import score_reached

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit: expansion scoring -----------------------------------------------


def test_score_reached_decays_and_dedups():
    seeds = {"S": 0.030}
    rows = [
        {"seed_id": "S", "id": "A", "title": "A", "slug": "a", "kind": "Concept", "hop": 1},
        {"seed_id": "S", "id": "A", "title": "A", "slug": "a", "kind": "Concept", "hop": 2},
        {"seed_id": "S", "id": "B", "title": "B", "slug": "b", "kind": "Source", "hop": 2},
    ]
    out = score_reached(seeds, rows, decay=0.5, weight=0.3)
    by_id = {r["entity_id"]: r for r in out.reached}
    # A: best (shortest) hop wins -> hop 1 -> 0.030 * 0.3 * 0.5^0
    assert by_id["A"]["hop"] == 1
    assert round(by_id["A"]["score"], 5) == round(0.030 * 0.3, 5)
    # B: hop 2 -> 0.030 * 0.3 * 0.5
    assert round(by_id["B"]["score"], 5) == round(0.030 * 0.3 * 0.5, 5)
    # Every expansion score is below the seed's own score (no displacement).
    assert all(r["score"] < seeds["S"] for r in out.reached)
    assert out.payload is not None


def test_score_reached_empty_is_no_payload():
    assert score_reached({"S": 0.1}, [], decay=0.5, weight=0.3).payload is None


# --- integration -----------------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def curation_env(monkeypatch, tmp_path):
    """A seeded corpus (source page + chunks + indexes + graph). Skips if a store
    is unreachable. No concept page yet, so 'team learning' is a genuine gap."""
    from compendium.graph.client import graph_driver, graph_reachable
    from compendium.index.clients import (
        opensearch_client, opensearch_reachable, qdrant_client, qdrant_reachable,
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
    gd = graph_driver()
    if not graph_reachable(gd):
        gd.close()
        pytest.skip("Memgraph unreachable")
    gd.close()

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
    monkeypatch.setenv("COMPENDIUM_SYNTH_STUB", "1")

    from compendium.graph.rebuild import rebuild
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")
    rebuild()
    yield test_url, str(vault)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _force_gap_trace(query: str) -> None:
    """Run a query against emptied pages indexes so it records a coverage-0 trace."""
    from compendium.index.clients import opensearch_client, qdrant_client
    from compendium.index import opensearch, qdrant
    from compendium.retrieve.pipeline import query as run_query

    opensearch.recreate_index(opensearch_client(), opensearch.PAGES_INDEX)
    qdrant.recreate_collection(qdrant_client(), qdrant.PAGES_COLLECTION)
    run_query(query)  # 0 pages -> coverage 0 -> fallback, persisted


def test_curate_run_writes_signals_and_dedups(curation_env):
    from compendium.curate.run import run as curate_run
    from compendium.db.connection import connection

    _force_gap_trace("team learning")
    report = curate_run()
    assert report.inserted >= 1
    assert "low_coverage_query" in report.by_kind
    with connection() as conn:
        runs = conn.execute(
            "SELECT signal_count FROM graph_analysis_runs WHERE completed_at IS NOT NULL"
        ).fetchall()
    assert runs and runs[-1]["signal_count"] == report.inserted
    # Re-run with no new conditions -> no duplicates.
    assert curate_run().inserted == 0


def test_curate_run_memgraph_down_still_yields_postgres_signals(curation_env, monkeypatch):
    from compendium.curate.run import run as curate_run

    monkeypatch.setenv("MEMGRAPH_URL", "bolt://localhost:7699")  # dead port
    _force_gap_trace("team learning")
    report = curate_run()
    assert "low_coverage_query" in report.by_kind
    assert "thin_grounding" in report.skipped_generators


def test_expansion_logs_graph_expansion(curation_env):
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.graph.links import link
    from compendium.retrieve.pipeline import run

    # With no semantic edges, expansion is a no-op.
    r0 = asyncio.run(run("psychological safety"))
    assert r0.trace["graph_expansion"] is None

    # Synthesize a concept (so we have two pages to link), reindex, then link.
    from compendium.wiki.synth import synthesize_concept
    from compendium.index.sync import reindex
    with connection() as conn:
        synthesize_concept(conn, "psychological safety", aliases=[], vault_path=curation_env[1])
    reindex("all")
    from compendium.graph.rebuild import rebuild
    rebuild()
    link("psychological-safety", "sample-markdown-source", "RELATED_TO")

    r1 = asyncio.run(run("psychological safety"))
    assert r1.trace["graph_expansion"] is not None
    assert r1.trace["graph_expansion"]["reached"]


def test_acceptance_loop(curation_env):
    """gap -> signal -> synth -> promote -> the original query's replay improves."""
    from compendium.curate.run import run as curate_run
    from compendium.curate.synth import synth_from_signal
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.index.sync import reindex
    from compendium.trace.promote import promote
    from compendium.trace.replay import replay

    # 1) A gap: 'psychological safety' has chunks but no concept page yet.
    _force_gap_trace("psychological safety")
    reindex("all")  # restore the pages index after the forced gap
    with connection() as conn:
        gap_trace_id = str(repository.list_query_traces(conn, 1)[0]["id"])

    # 2) Slow loop surfaces a matching signal.
    curate_run()
    with connection() as conn:
        sig = next(s for s in repository.list_open_signals(conn)
                   if s["kind"] == "low_coverage_query"
                   and "psychological safety" in s["payload"].get("query_text", ""))

    # 3) Synthesize from the signal -> a draft that cites chunks.
    slug = synth_from_signal(str(sig["id"]))
    with connection() as conn:
        page = repository.resolve_page_by_slug(conn, slug)
        assert page["status"] == "draft"
        revs = repository.get_page_revisions(conn, page["id"])
        assert revs  # has a revision

    # 4) Promote -> signal addressed, SYNTHESIZES edges, page indexed.
    promote(slug, "canonical", vault_path=curation_env[1])
    reindex("all")
    with connection() as conn:
        sig_after = repository.get_curation_signal(conn, sig["id"])
        assert sig_after["status"] == "addressed"
        assert sig_after["addressed_revision_id"] is not None

    # 5) Replaying the original gap query now finds the new page (improved).
    result = replay(gap_trace_id)
    assert result.replayed_coverage > (result.original_coverage or 0.0)
    assert result.diff.added  # the original had no pages; now the wiki answers


def test_tui_curation_synth_action(curation_env):
    from textual.widgets import DataTable
    from compendium.curate.run import run as curate_run
    from compendium.tui.app import CompendiumTUI
    from compendium.tui.screens.curation import CurationScreen

    _force_gap_trace("psychological safety")
    from compendium.index.sync import reindex
    reindex("all")
    curate_run()

    async def body():
        app = CompendiumTUI()
        async with app.run_test() as pilot:
            await pilot.press("c"); await pilot.pause()
            await app.workers.wait_for_complete(); await pilot.pause()
            assert isinstance(app.screen, CurationScreen)
            before = app.screen.query_one("#signals", DataTable).row_count
            assert before >= 1
            await pilot.press("y"); await pilot.pause()
            await app.workers.wait_for_complete(); await pilot.pause()
            after = app.screen.query_one("#signals", DataTable).row_count
            assert after == before - 1  # the synthesized signal left the open queue

    asyncio.run(body())
