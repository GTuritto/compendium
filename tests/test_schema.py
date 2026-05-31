"""Phase 1 schema integration test.

Runs the migrations against a dedicated ``compendium_test`` database, so the
dev ``compendium`` database is never touched. Skips when PostgreSQL is
unreachable (for example, when Docker is not running).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.rows import dict_row

from compendium.config import load_config
from compendium.db import repository

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEST_DB = "compendium_test"

_TABLES = {
    "sources",
    "source_documents",
    "corpus_revisions",
    "chunks",
    "wiki_pages",
    "wiki_pages_topics",
    "wiki_page_revisions",
    "index_sync_state",
    "promotion_events",
    "query_traces",
    "ask_traces",
    "graph_curation_signals",
    "graph_analysis_runs",
}
_VIEWS = {
    "v_sync_lag",
    "v_failed_sources",
    "v_recent_traces",
    "v_open_curation_signals",
}


def _swap_db(url: str, dbname: str) -> str:
    """Return ``url`` with its database name replaced by ``dbname``."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture(scope="module")
def test_db_url() -> str:
    """Drop and recreate compendium_test; yield its URL. Skip if PG is down."""
    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    with admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {_TEST_DB}")
    yield _swap_db(base, _TEST_DB)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={db_url}"])
    return cfg


def test_upgrade_builds_schema_and_round_trip(test_db_url: str) -> None:
    command.upgrade(_alembic_cfg(test_db_url), "head")

    with psycopg.connect(test_db_url) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        enum_count = conn.execute(
            "SELECT count(*) FROM pg_type WHERE typtype = 'e'"
        ).fetchone()[0]
        views = {
            r[0]
            for r in conn.execute(
                "SELECT viewname FROM pg_views WHERE schemaname = 'public'"
            )
        }
        assert _TABLES <= tables
        assert enum_count == 10
        assert _VIEWS <= views
        for view in _VIEWS:
            conn.execute(f"SELECT * FROM {view}").fetchall()  # queryable

    # Round-trip a stub source and wiki_page through the access layer.
    with psycopg.connect(test_db_url, row_factory=dict_row) as conn:
        source_id = repository.insert_source(
            conn,
            kind="book",
            title="Stub Source",
            content_hash="h-source",
            author="A. Author",
            year=2020,
            metadata={"isbn": "000"},
        )
        page_id = repository.insert_wiki_page(
            conn,
            kind="concept",
            slug="stub",
            title="Stub Page",
            file_path="vault/concepts/stub.md",
            content_hash="h-page",
            aliases=["one", "two"],
        )
        conn.commit()
        source = repository.get_source(conn, source_id)
        page = repository.get_wiki_page(conn, page_id)

    assert source is not None and page is not None
    assert source["kind"] == "book"
    assert source["title"] == "Stub Source"
    assert source["year"] == 2020
    assert source["metadata"] == {"isbn": "000"}
    assert page["kind"] == "concept"
    assert page["slug"] == "stub"
    assert page["status"] == "draft"
    assert page["aliases"] == ["one", "two"]


def test_downgrade_reverses(test_db_url: str) -> None:
    cfg = _alembic_cfg(test_db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    with psycopg.connect(test_db_url) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        enum_count = conn.execute(
            "SELECT count(*) FROM pg_type WHERE typtype = 'e'"
        ).fetchone()[0]

    # Only alembic_version may remain; no operational tables, no enums.
    assert _TABLES.isdisjoint(tables)
    assert enum_count == 0
