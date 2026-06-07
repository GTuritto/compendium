"""The gate: `graph rebuild` replays semantic edges instead of wiping them
(arch-semantic-edge-persistence).

Integration tests: need a migrated ``compendium_test`` database and a running
Memgraph; skip if either is unreachable. These are the regression guard for the
data-loss defect that motivated the whole change.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.db import repository
from compendium.graph import schema, semantic_edges

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def conn_and_driver(monkeypatch):
    """A migrated compendium_test conn + a clean Memgraph. Skips if down."""
    from compendium.graph.client import graph_driver, graph_reachable

    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    driver = graph_driver()
    if not graph_reachable(driver):
        driver.close()
        pytest.skip("Memgraph unreachable")

    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")

    schema.drop_all(driver)
    schema.ensure_indexes(driver)
    monkeypatch.setenv("POSTGRES_URL", test_url)
    monkeypatch.setenv("VAULT_PATH", str(_REPO_ROOT / "tests"))  # unused; rebuild needs a path
    from compendium.db.connection import connection

    with connection() as conn:
        yield conn, driver

    driver.close()
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _edge(driver, edge_type, from_id, to_id):
    from compendium.graph.client import run_cypher

    rows = run_cypher(
        driver,
        f"MATCH (a {{id: $a}})-[r:{edge_type}]->(b {{id: $b}}) "
        "RETURN r.extracted_by AS by, r.confidence AS confidence, r.model AS model",
        a=from_id, b=to_id,
    )
    return rows[0] if rows else None


def test_rebuild_preserves_curator_synthesizes_and_llm_edges(conn_and_driver):
    conn, driver = conn_and_driver

    # A curator edge, a SYNTHESIZES edge, and an LLM-extracted edge.
    semantic_edges.record_semantic_edge(
        conn, driver, "RELATED_TO", "Concept", "c1", "Concept", "c2",
        provenance={"weight": 1.0, "extracted_by": "curator"},
    )
    semantic_edges.record_semantic_edge(
        conn, driver, "SYNTHESIZES", "Concept", "c1", "Source", "s1",
        provenance={"extracted_by": "curator"},
    )
    semantic_edges.record_extracted_edge(
        conn, driver, "PREREQUISITE_FOR", "Concept", "c3", "Concept", "c4",
        {"extracted_by": "llm", "model": "m", "confidence": 0.81,
         "extracted_at": "2026-06-07T00:00:00Z", "source_revision_id": "", "weight": 0.81},
    )
    conn.commit()

    # The whole point: a rebuild used to wipe all three. Now it replays them.
    from compendium.graph.rebuild import rebuild

    report = rebuild()
    assert report.edges["RELATED_TO"] == 1
    assert report.edges["SYNTHESIZES"] == 1
    assert report.edges["PREREQUISITE_FOR"] == 1

    assert _edge(driver, "RELATED_TO", "c1", "c2")["by"] == "curator"
    assert _edge(driver, "SYNTHESIZES", "c1", "s1")["by"] == "curator"
    llm = _edge(driver, "PREREQUISITE_FOR", "c3", "c4")
    assert llm["by"] == "llm" and llm["confidence"] == pytest.approx(0.81) and llm["model"] == "m"


def test_curator_protection_survives_a_rebuild(conn_and_driver):
    conn, driver = conn_and_driver
    # Curator edge, then an LLM proposal for the same pair (collision, dropped).
    semantic_edges.record_semantic_edge(
        conn, driver, "RELATED_TO", "Concept", "a", "Concept", "b",
        provenance={"weight": 1.0, "extracted_by": "curator"},
    )
    disp = semantic_edges.record_extracted_edge(
        conn, driver, "RELATED_TO", "Concept", "a", "Concept", "b",
        {"extracted_by": "llm", "model": "m", "confidence": 0.9,
         "extracted_at": "2026-06-07T00:00:00Z", "source_revision_id": "", "weight": 0.9},
    )
    assert disp == "collision"
    conn.commit()

    from compendium.graph.rebuild import rebuild

    rebuild()
    # Still exactly one curator edge after the rebuild.
    assert _edge(driver, "RELATED_TO", "a", "b")["by"] == "curator"
    assert len(repository.all_semantic_edges(conn)) == 1


def test_backfill_captures_in_graph_only_edges_then_rebuild_preserves(conn_and_driver):
    conn, driver = conn_and_driver
    # Simulate a pre-fix edge: write straight to the graph, no PostgreSQL row.
    schema.upsert_semantic_edge(
        driver, "RELATED_TO", "Concept", "x", "Concept", "y",
        provenance={"weight": 1.0, "extracted_by": "curator"},
    )
    assert repository.all_semantic_edges(conn) == []

    captured = semantic_edges.backfill_edges()
    assert captured == 1
    # backfill opened its own connection; re-read on a fresh connection.
    from compendium.db.connection import connection

    with connection() as c2:
        rows = repository.all_semantic_edges(c2)
        assert len(rows) == 1 and rows[0]["from_id"] == "x"
        # Idempotent: a second backfill inserts no duplicate.
        assert semantic_edges.backfill_edges() == 1
        assert len(repository.all_semantic_edges(c2)) == 1

    from compendium.graph.rebuild import rebuild

    rebuild()
    assert _edge(driver, "RELATED_TO", "x", "y")["by"] == "curator"
