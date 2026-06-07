"""The dual-write coordinator writes the resolved edge to both stores
(arch-semantic-edge-persistence).

Integration tests: need a migrated ``compendium_test`` database and a running
Memgraph; skip if either is unreachable. The graph stays the arbiter of
curator-protection / canonicalisation; these assert PostgreSQL mirrors the
resolved outcome.
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

    schema.drop_all(driver)  # a clean graph for this test
    monkeypatch.setenv("POSTGRES_URL", test_url)
    from compendium.db.connection import connection

    with connection() as conn:
        yield conn, driver

    driver.close()
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _edge_extracted_by(driver, edge_type, from_id, to_id):
    from compendium.graph.client import run_cypher

    rows = run_cypher(
        driver,
        f"MATCH (a {{id: $a}})-[r:{edge_type}]->(b {{id: $b}}) RETURN r.extracted_by AS by",
        a=from_id, b=to_id,
    )
    return rows[0]["by"] if rows else None


def test_curator_link_writes_both_stores(conn_and_driver):
    conn, driver = conn_and_driver
    disp = semantic_edges.record_semantic_edge(
        conn, driver, "RELATED_TO", "Concept", "e", "Concept", "f",
        provenance={"weight": 1.0, "extracted_by": "curator"},
    )
    assert disp == "written"
    assert _edge_extracted_by(driver, "RELATED_TO", "e", "f") == "curator"
    rows = repository.all_semantic_edges(conn)
    assert len(rows) == 1 and rows[0]["from_id"] == "e" and rows[0]["extracted_by"] == "curator"


def test_llm_collision_touches_neither_store(conn_and_driver):
    conn, driver = conn_and_driver
    semantic_edges.record_semantic_edge(
        conn, driver, "RELATED_TO", "Concept", "a", "Concept", "b",
        provenance={"weight": 1.0, "extracted_by": "curator"},
    )
    llm = {"extracted_by": "llm", "model": "m", "confidence": 0.9,
           "extracted_at": "2026-06-07T00:00:00Z", "source_revision_id": "", "weight": 0.9}
    disp = semantic_edges.record_semantic_edge(
        conn, driver, "RELATED_TO", "Concept", "a", "Concept", "b", provenance=llm,
    )
    assert disp == "collision"
    # Graph edge keeps curator provenance; PostgreSQL still has the one curator row.
    assert _edge_extracted_by(driver, "RELATED_TO", "a", "b") == "curator"
    rows = repository.all_semantic_edges(conn)
    assert len(rows) == 1 and rows[0]["extracted_by"] == "curator"


def test_llm_refresh_updates_both_stores(conn_and_driver):
    conn, driver = conn_and_driver
    llm = {"extracted_by": "llm", "model": "m", "confidence": 0.7,
           "extracted_at": "2026-06-07T00:00:00Z", "source_revision_id": "", "weight": 0.7}
    assert semantic_edges.record_extracted_edge(
        conn, driver, "PREREQUISITE_FOR", "Concept", "c", "Concept", "d", llm
    ) == "written"
    disp = semantic_edges.record_extracted_edge(
        conn, driver, "PREREQUISITE_FOR", "Concept", "c", "Concept", "d", llm
    )
    assert disp == "refreshed"
    rows = repository.all_semantic_edges(conn)
    assert len(rows) == 1 and rows[0]["extracted_by"] == "llm"
