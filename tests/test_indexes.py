"""Phase 4 derived-index tests: projection units plus an integration walk.

Unit tests run anywhere. Integration tests need a migrated ``compendium_test``
database (skipped if PostgreSQL is unreachable) and running OpenSearch and
Qdrant (skipped if either is unreachable). They always use the deterministic
stub embedder, so no embeddings endpoint is required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.index import documents
from compendium.index.embedder import EMBED_DIM, StubEmbedder

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UUID = "11111111-1111-1111-1111-111111111111"
_SRC = "22222222-2222-2222-2222-222222222222"
_TOPIC = "33333333-3333-3333-3333-333333333333"


# --- unit: projection ------------------------------------------------------


def _page_row() -> dict:
    return {
        "id": _UUID,
        "kind": "concept",
        "title": "Psychological Safety",
        "slug": "psychological-safety",
        "status": "canonical",
        "corpus_revision": "rev-x",
        "parent_topic_id": None,
        "source_id": None,
        "source_kind": None,
        "inspection_status": None,
        "aliases": ["psych safety"],
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def test_page_projection_carries_documented_fields():
    body = "# Psychological Safety\n\nA shared belief about interpersonal risk."
    doc = documents.page_document(_page_row(), body=body, topic_ids=[_TOPIC])
    assert doc["id"] == _UUID
    assert doc["kind"] == "concept"
    assert doc["topic_ids"] == [_TOPIC]
    assert doc["aliases"] == ["psych safety"]
    assert doc["body"] == body
    assert doc["created_at"] == _NOW.isoformat()  # OpenSearch wants ISO

    payload = documents.page_payload(_page_row(), topic_ids=[_TOPIC])
    assert payload["id"] == _UUID
    assert payload["topic_ids"] == [_TOPIC]
    assert "body" not in payload  # the page body is not stored in Qdrant
    assert payload["created_at"] == int(_NOW.timestamp() * 1000)  # Qdrant wants ms


def test_chunk_projection_carries_documented_fields():
    chunk = {
        "id": _UUID,
        "source_id": _SRC,
        "source_kind": "note",
        "source_title": "Sample Markdown Source",
        "position": 3,
        "parent_section": "Team Learning",
        "body": "Teams that learn well treat errors as information.",
        "token_count": 9,
        "created_at": _NOW,
    }
    doc = documents.chunk_document(chunk)
    assert doc["source_id"] == _SRC
    assert doc["source_title"] == "Sample Markdown Source"
    assert doc["position"] == 3
    assert doc["body"] == chunk["body"]

    payload = documents.chunk_payload(chunk)
    assert payload["source_id"] == _SRC
    assert payload["position"] == 3
    assert payload["body_preview"].startswith("Teams that learn")
    assert "body" not in payload  # only a preview lives in Qdrant


def test_stub_embedder_is_deterministic_and_offline():
    embedder = StubEmbedder()
    a, b, c = embedder.embed(["same text", "same text", "different"])
    assert len(a) == EMBED_DIM
    assert a == b  # identical input -> identical vector
    assert a != c


# --- integration -----------------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def index_env(monkeypatch, tmp_path):
    """A migrated DB, a temp vault, the stub embedder, and reachable stores."""
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
    yield test_url, str(vault)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _db_counts(db_url: str) -> tuple[int, int]:
    with psycopg.connect(db_url) as conn:
        pages = conn.execute("SELECT count(*) FROM wiki_pages").fetchone()[0]
        chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    return pages, chunks


def test_enqueue_idempotency_resets_indexed_rows(index_env):
    db_url, _ = index_env
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")

    with connection() as conn:
        page_id = repository.all_wiki_page_ids(conn)[0]
        # Pretend the page's rows were already indexed.
        rows = conn.execute(
            "SELECT id FROM index_sync_state WHERE entity_id = %s", (page_id,)
        ).fetchall()
        for row in rows:
            repository.mark_sync_indexed(conn, row["id"])
        assert all(
            r["state"] == "indexed"
            for r in conn.execute(
                "SELECT state FROM index_sync_state WHERE entity_id = %s", (page_id,)
            )
        )
        # Re-enqueue resets them to pending with attempts cleared. A page write
        # enqueues all three page-relevant kinds (memgraph added in Phase 6).
        repository.enqueue_index(
            conn, entity_kind="page", entity_id=page_id,
            index_kinds=("opensearch_pages", "qdrant_pages", "memgraph"),
        )
        reset = conn.execute(
            "SELECT state, attempts FROM index_sync_state WHERE entity_id = %s",
            (page_id,),
        ).fetchall()
    assert {r["state"] for r in reset} == {"pending"}
    assert all(r["attempts"] == 0 for r in reset)


def test_drain_populates_both_indexes(index_env):
    db_url, _ = index_env
    from compendium.index import opensearch, qdrant
    from compendium.index.clients import opensearch_client, qdrant_client
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    ingest(str(_FIXTURES / "sample.pdf"), kind="paper")

    report = reindex("all")
    assert report.failed == 0

    page_count, chunk_count = _db_counts(db_url)
    assert page_count > 0 and chunk_count > 0

    os_client, q_client = opensearch_client(), qdrant_client()
    assert opensearch.count(os_client, opensearch.PAGES_INDEX) == page_count
    assert opensearch.count(os_client, opensearch.CHUNKS_INDEX) == chunk_count
    assert qdrant.count(q_client, qdrant.PAGES_COLLECTION) == page_count
    assert qdrant.count(q_client, qdrant.CHUNKS_COLLECTION) == chunk_count

    with psycopg.connect(db_url) as conn:
        # reindex drains only the OpenSearch/Qdrant kinds; the memgraph kind is
        # drained separately (compendium graph rebuild), so exclude it here.
        pending = conn.execute(
            "SELECT count(*) FROM index_sync_state "
            "WHERE state <> 'indexed' AND index_kind <> 'memgraph'"
        ).fetchone()[0]
    assert pending == 0


def test_known_query_returns_relevant_hit(index_env):
    from compendium.index import qdrant
    from compendium.index.clients import opensearch_client, qdrant_client
    from compendium.index.embedder import StubEmbedder
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")

    # OpenSearch: a real BM25 body match returns the source page.
    os_client = opensearch_client()
    hits = os_client.search(
        index="pages", body={"query": {"match": {"body": "psychological safety"}}}
    )
    assert hits["hits"]["total"]["value"] >= 1

    # Qdrant: embedding a stored chunk's body returns that chunk as top hit
    # (the stub is deterministic, so cosine similarity to itself is maximal).
    q_client = qdrant_client()
    with psycopg.connect(load_config().postgres_url) as conn:
        chunk = conn.execute(
            "SELECT id, body FROM chunks ORDER BY position LIMIT 1"
        ).fetchone()
    vector = StubEmbedder().embed([chunk[1]])[0]
    found = q_client.query_points(
        collection_name=qdrant.CHUNKS_COLLECTION, query=vector, limit=1
    ).points
    assert found and str(found[0].id) == str(chunk[0])


def test_reindex_from_empty_restores_state(index_env):
    from compendium.index import opensearch, qdrant
    from compendium.index.clients import opensearch_client, qdrant_client
    from compendium.index.embedder import StubEmbedder
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")

    os_client, q_client = opensearch_client(), qdrant_client()
    page_count, chunk_count = _db_counts(index_env[0])

    # A fixed query's top-K page ids before the rebuild.
    vector = StubEmbedder().embed(["psychological safety and team learning"])[0]

    def top_k_ids() -> set[str]:
        pts = q_client.query_points(
            collection_name=qdrant.PAGES_COLLECTION, query=vector, limit=10
        ).points
        return {str(p.id) for p in pts}

    before = top_k_ids()

    # Drop everything and rebuild from PostgreSQL plus the vault.
    opensearch.recreate_index(os_client, opensearch.PAGES_INDEX)
    opensearch.recreate_index(os_client, opensearch.CHUNKS_INDEX)
    qdrant.recreate_collection(q_client, qdrant.PAGES_COLLECTION)
    qdrant.recreate_collection(q_client, qdrant.CHUNKS_COLLECTION)
    assert opensearch.count(os_client, opensearch.PAGES_INDEX) == 0
    assert qdrant.count(q_client, qdrant.PAGES_COLLECTION) == 0

    report = reindex("all")
    assert report.failed == 0
    assert opensearch.count(os_client, opensearch.PAGES_INDEX) == page_count
    assert opensearch.count(os_client, opensearch.CHUNKS_INDEX) == chunk_count
    assert qdrant.count(q_client, qdrant.PAGES_COLLECTION) == page_count

    after = top_k_ids()
    # Qdrant HNSW is not byte-deterministic; require top-K Jaccard >= 0.6.
    union = before | after
    jaccard = len(before & after) / len(union) if union else 1.0
    assert jaccard >= 0.6


# --- arch-index-document-shape: the contract, frozen -------------------------


def test_page_wire_format_is_frozen():
    """The exact dicts sent to the stores — byte-for-byte the pre-shape output."""
    body = "# T\n\nB."
    doc = documents.page_document(_page_row(), body=body, topic_ids=[_TOPIC])
    assert doc == {
        "id": _UUID,
        "kind": "concept",
        "title": "Psychological Safety",
        "slug": "psychological-safety",
        "status": "canonical",
        "corpus_revision": "rev-x",
        "tags": [],
        "topic_ids": [_TOPIC],
        "parent_topic_id": None,
        "source_id": None,
        "source_kind": None,
        "inspection_status": None,
        "aliases": ["psych safety"],
        "body": body,
        "created_at": _NOW.isoformat(),
        "updated_at": _NOW.isoformat(),
    }
    payload = documents.page_payload(_page_row(), topic_ids=[_TOPIC])
    assert payload == {
        "id": _UUID,
        "kind": "concept",
        "title": "Psychological Safety",
        "slug": "psychological-safety",
        "status": "canonical",
        "corpus_revision": "rev-x",
        "tags": [],
        "topic_ids": [_TOPIC],
        "parent_topic_id": None,
        "source_id": None,
        "source_kind": None,
        "created_at": int(_NOW.timestamp() * 1000),
        "updated_at": int(_NOW.timestamp() * 1000),
    }


def test_chunk_wire_format_is_frozen():
    chunk = {
        "id": _UUID,
        "source_id": _SRC,
        "source_kind": "note",
        "source_title": "S",
        "position": 1,
        "parent_section": None,
        "body": "  Teams   learn  well.  ",
        "token_count": 4,
        "created_at": _NOW,
    }
    assert documents.chunk_document(chunk) == {
        "id": _UUID,
        "source_id": _SRC,
        "source_kind": "note",
        "tags": [],
        "source_title": "S",
        "position": 1,
        "parent_section": None,
        "body": "  Teams   learn  well.  ",
        "token_count": 4,
        "created_at": _NOW.isoformat(),
    }
    assert documents.chunk_payload(chunk) == {
        "id": _UUID,
        "source_id": _SRC,
        "source_kind": "note",
        "tags": [],
        "position": 1,
        "parent_section": None,
        "body_preview": "Teams learn well.",
        "token_count": 4,
        "created_at": int(_NOW.timestamp() * 1000),
    }


def test_builders_agree_with_the_field_constants():
    body = "b"
    assert tuple(documents.page_document(_page_row(), body=body, topic_ids=[])) == documents.PAGE_DOCUMENT_FIELDS
    assert tuple(documents.page_payload(_page_row(), topic_ids=[])) == documents.PAGE_PAYLOAD_FIELDS
    chunk = {
        "id": _UUID, "source_id": _SRC, "position": 0, "body": "x",
        "created_at": _NOW,
    }
    assert tuple(documents.chunk_document(chunk)) == documents.CHUNK_DOCUMENT_FIELDS
    assert tuple(documents.chunk_payload(chunk)) == documents.CHUNK_PAYLOAD_FIELDS


def test_opensearch_mappings_agree_with_the_shape():
    """A renamed shape field (or mapping property) fails here, not silently."""
    from compendium.index import opensearch

    pages_props = opensearch._pages_body()["mappings"]["properties"]
    chunks_props = opensearch._chunks_body()["mappings"]["properties"]
    assert set(pages_props) == set(documents.PAGE_DOCUMENT_FIELDS)
    assert set(chunks_props) == set(documents.CHUNK_DOCUMENT_FIELDS)


def test_searchable_subsets_are_shape_members():
    assert set(documents.PAGE_SEARCHABLE_FIELDS) <= set(documents.PAGE_DOCUMENT_FIELDS)
    assert set(documents.CHUNK_SEARCHABLE_FIELDS) <= set(documents.CHUNK_DOCUMENT_FIELDS)


def test_display_fields_preview_owns_the_store_difference():
    from compendium.retrieve.fusion import FusedHit
    from compendium.retrieve.search import Hit

    os_hit = Hit(entity_id="e", score=1.0, fields={"body": "full body"})
    qd_hit = Hit(entity_id="e", score=1.0, fields={"body_preview": "short"})
    assert os_hit.preview == "full body"
    assert qd_hit.preview == "short"
    fused = FusedHit(entity_id="e", score=1.0, fields={"title": "T", "slug": "t"})
    assert (fused.title, fused.slug, fused.kind) == ("T", "t", "")
