"""Hard delete of a source (ADR-018, v0.5).

Integration tests: need a migrated ``compendium_test`` database; skip if
PostgreSQL is unreachable. The best-effort derived-store cleanup is stubbed so
these tests assert the canonical (PostgreSQL) deletion deterministically; the
derived path is exercised by the manual smoke playbook against live stores.
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


def _chunk(position: int, body: str) -> SimpleNamespace:
    return SimpleNamespace(
        position=position,
        parent_section=None,
        body=body,
        body_hash=f"hash-{position}",
        token_count=len(body.split()),
    )


def _seed_source(conn) -> dict:
    """Insert a source with two chunks, a source page, a semantic edge, and
    sync-state rows. Returns the ids. Commits so a second connection sees it."""
    source_id = repository.insert_source(
        conn, kind="note", title="Doomed Source", content_hash="ch-doomed"
    )
    repository.insert_chunks(conn, source_id, [_chunk(0, "alpha"), _chunk(1, "beta")])
    chunk_ids = repository.all_chunk_ids_for_source(conn, source_id)
    page_id = repository.insert_wiki_page(
        conn,
        kind="source",
        slug="doomed-source",
        title="Doomed Source",
        file_path="sources/doomed-source.md",
        content_hash="pageh",
        source_id=source_id,
        source_kind="note",
    )
    # a semantic edge from the source node, and sync rows for page + a chunk
    conn.execute(
        """
        INSERT INTO semantic_edges
            (edge_type, from_label, from_id, to_label, to_id, extracted_by)
        VALUES ('RELATED_TO', 'Source', %s, 'Concept', %s, 'curator')
        """,
        (str(source_id), "some-concept-id"),
    )
    conn.execute(
        """
        INSERT INTO index_sync_state (entity_kind, entity_id, index_kind, state)
        VALUES ('page', %s, 'opensearch_pages', 'indexed'),
               ('chunk', %s, 'opensearch_chunks', 'indexed')
        """,
        (str(page_id), str(chunk_ids[0])),
    )
    conn.commit()
    return {"source_id": source_id, "page_id": page_id, "chunk_ids": chunk_ids}


@pytest.fixture(autouse=True)
def _stub_derived(monkeypatch):
    """Stub the best-effort derived-store cleanup (no live OS/Qdrant/Memgraph)."""
    monkeypatch.setattr(
        "compendium.maintenance.delete._delete_derived",
        lambda *a, **k: None,
    )


def test_dry_run_removes_nothing(migrated_conn):
    from compendium.maintenance import delete

    ids = _seed_source(migrated_conn)
    report = delete.delete_source("doomed-source", dry_run=True)

    assert report.found is True
    assert report.dry_run is True
    assert report.chunk_count == 2
    assert report.slug == "doomed-source"
    # nothing removed
    assert repository.get_source(migrated_conn, ids["source_id"]) is not None
    assert repository.count_chunks(migrated_conn, ids["source_id"]) == 2


def test_hard_delete_purges_everything(migrated_conn):
    from compendium.maintenance import delete

    ids = _seed_source(migrated_conn)
    report = delete.delete_source("doomed-source", dry_run=False)

    assert report.found is True
    assert report.page_removed is True
    assert report.chunk_count == 2
    assert report.semantic_edges_removed == 1

    # a fresh read on the same DB: source, chunks, page all gone
    migrated_conn.rollback()  # drop our snapshot; re-read committed state
    assert repository.get_source(migrated_conn, ids["source_id"]) is None
    assert repository.get_wiki_page_by_source_id(migrated_conn, ids["source_id"]) is None
    rows = migrated_conn.execute(
        "SELECT count(*) AS n FROM chunks WHERE source_id = %s", (ids["source_id"],)
    ).fetchone()
    assert rows["n"] == 0
    edges = migrated_conn.execute(
        "SELECT count(*) AS n FROM semantic_edges WHERE from_id = %s",
        (str(ids["source_id"]),),
    ).fetchone()
    assert edges["n"] == 0
    sync = migrated_conn.execute(
        "SELECT count(*) AS n FROM index_sync_state WHERE entity_id = %s",
        (str(ids["page_id"]),),
    ).fetchone()
    assert sync["n"] == 0


def test_delete_by_source_id_and_missing(migrated_conn):
    from compendium.maintenance import delete

    ids = _seed_source(migrated_conn)
    # resolve by raw source id works
    report = delete.delete_source(str(ids["source_id"]), dry_run=True)
    assert report.found is True

    # unknown identifier reports not found
    missing = delete.delete_source("no-such-slug", dry_run=True)
    assert missing.found is False
