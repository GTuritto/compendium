"""Tags repository round-trip (ADR-019, v0.5).

Integration: needs a migrated ``compendium_test`` DB (incl. migration 0015);
skips if PostgreSQL is unreachable. System-of-record layer only.
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


def test_tag_source_and_page(migrated_conn):
    conn = migrated_conn
    source_id = repository.insert_source(
        conn, kind="note", title="Tagged", content_hash="h1"
    )
    page_id = repository.insert_wiki_page(
        conn, kind="concept", slug="tagged-concept", title="Tagged Concept",
        file_path="concepts/tagged-concept.md", content_hash="ph",
    )

    repository.add_source_tag(conn, source_id, "trading")
    repository.add_source_tag(conn, source_id, "to-reread")
    repository.add_source_tag(conn, source_id, "trading")  # idempotent
    repository.add_page_tag(conn, page_id, "trading")

    assert repository.tags_for_source(conn, source_id) == ["to-reread", "trading"]
    assert repository.tags_for_page(conn, page_id) == ["trading"]

    # usage counts: 'trading' on 1 source + 1 page; 'to-reread' on 1 source
    counts = {r["name"]: (r["sources"], r["pages"]) for r in repository.list_tags(conn)}
    assert counts["trading"] == (1, 1)
    assert counts["to-reread"] == (1, 0)


def test_remove_tag(migrated_conn):
    conn = migrated_conn
    source_id = repository.insert_source(
        conn, kind="note", title="T2", content_hash="h2"
    )
    repository.add_source_tag(conn, source_id, "x")
    repository.remove_source_tag(conn, source_id, "x")
    assert repository.tags_for_source(conn, source_id) == []
    # the tag definition persists even with no attachments
    assert any(r["name"] == "x" for r in repository.list_tags(conn))


def test_source_delete_cascades_tag_links(migrated_conn):
    conn = migrated_conn
    source_id = repository.insert_source(
        conn, kind="note", title="T3", content_hash="h3"
    )
    repository.add_source_tag(conn, source_id, "y")
    repository.delete_source_row(conn, source_id)  # ADR-018 cascade
    assert repository.tags_for_source(conn, source_id) == []


def test_index_tags_inherit_from_source(migrated_conn):
    """TC-TAG-U3: source tags inherit to the source page and its chunks; a
    concept page carries only its own tags; the index document carries them."""
    from compendium.index import documents, projectors

    conn = migrated_conn
    source_id = repository.insert_source(
        conn, kind="note", title="S", content_hash="hc"
    )
    src_page_id = repository.insert_wiki_page(
        conn, kind="source", slug="s-src", title="S",
        file_path="sources/s-src.md", content_hash="p",
        source_id=source_id, source_kind="note",
    )
    repository.add_source_tag(conn, source_id, "trading")

    src_page = repository.get_wiki_page(conn, src_page_id)
    assert projectors.page_tags(conn, src_page) == ["trading"]
    assert projectors.chunk_tags(conn, {"source_id": source_id}) == ["trading"]
    doc = documents.page_document(
        src_page, body="b", topic_ids=[], tags=projectors.page_tags(conn, src_page)
    )
    assert doc["tags"] == ["trading"]

    cpage_id = repository.insert_wiki_page(
        conn, kind="concept", slug="c", title="C",
        file_path="concepts/c.md", content_hash="pc",
    )
    repository.add_page_tag(conn, cpage_id, "x")
    cpage = repository.get_wiki_page(conn, cpage_id)
    assert projectors.page_tags(conn, cpage) == ["x"]
