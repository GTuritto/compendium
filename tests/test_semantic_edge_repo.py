"""Repository round-trip for the semantic_edges table (arch-semantic-edge-persistence).

Integration tests: need a migrated ``compendium_test`` database; skip if
PostgreSQL is unreachable. No graph or vault is involved here -- this is the
system-of-record layer only.
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

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def migrated_conn(monkeypatch):
    """A connection to a freshly migrated compendium_test DB. Skips if down."""
    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")

    monkeypatch.setenv("POSTGRES_URL", test_url)
    from compendium.db.connection import connection

    with connection() as conn:
        yield conn

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


_CURATOR = {"weight": 1.0, "extracted_by": "curator"}
_LLM = {
    "extracted_by": "llm",
    "model": "test-model",
    "confidence": 0.83,
    "extracted_at": "2026-06-07T00:00:00Z",
    "source_revision_id": "rev-1",
    "weight": 0.83,
}


def _key():
    return dict(
        edge_type="RELATED_TO",
        from_label="Concept", from_id="a",
        to_label="Concept", to_id="b",
    )


def test_upsert_then_read_round_trips_provenance(migrated_conn):
    repository.upsert_semantic_edge_row(migrated_conn, **_key(), provenance=_LLM)
    migrated_conn.commit()

    rows = repository.all_semantic_edges(migrated_conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["edge_type"] == "RELATED_TO"
    assert row["from_id"] == "a" and row["to_id"] == "b"
    assert row["extracted_by"] == "llm"
    assert row["model"] == "test-model"
    assert row["confidence"] == pytest.approx(0.83)
    assert row["source_revision_id"] == "rev-1"


def test_upsert_on_conflict_updates_in_place(migrated_conn):
    repository.upsert_semantic_edge_row(migrated_conn, **_key(), provenance=_LLM)
    # A curator write to the same directed pair refreshes, not duplicates.
    repository.upsert_semantic_edge_row(migrated_conn, **_key(), provenance=_CURATOR)
    migrated_conn.commit()

    rows = repository.all_semantic_edges(migrated_conn)
    assert len(rows) == 1
    assert rows[0]["extracted_by"] == "curator"
    assert rows[0]["weight"] == pytest.approx(1.0)
    # Absent keys are nulled out by the refresh.
    assert rows[0]["model"] is None
    assert rows[0]["confidence"] is None


def test_delete_removes_the_row(migrated_conn):
    repository.upsert_semantic_edge_row(migrated_conn, **_key(), provenance=_CURATOR)
    repository.delete_semantic_edge_row(migrated_conn, **_key())
    migrated_conn.commit()
    assert repository.all_semantic_edges(migrated_conn) == []
