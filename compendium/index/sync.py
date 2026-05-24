"""Drain the ``index_sync_state`` queue into OpenSearch and Qdrant.

Writes to ``wiki_pages`` and ``chunks`` enqueue ``pending`` sync rows in the
same transaction; this module is the separate, explicit step that drains them
(ADR-005, eventual consistency). It also drives ``compendium reindex``: drop
the target schemas, re-enqueue every entity, and drain from empty.

Each row is processed independently and committed on its own, so one failure
neither rolls back prior progress nor aborts the rest of the queue. A row whose
entity has since been deleted (a stale chunk after re-ingest) is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from compendium.config import load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.index import documents, opensearch, qdrant
from compendium.index.clients import opensearch_client, qdrant_client
from compendium.index.embedder import Embedder, get_embedder
from compendium.wiki.page import parse_markdown

# The index kinds that belong to each reindex target.
_PAGE_KINDS = ("opensearch_pages", "qdrant_pages")
_CHUNK_KINDS = ("opensearch_chunks", "qdrant_chunks")
_TARGET_KINDS = {
    "pages": _PAGE_KINDS,
    "chunks": _CHUNK_KINDS,
    "all": _PAGE_KINDS + _CHUNK_KINDS,
}


@dataclass
class SyncReport:
    """The outcome of a drain: per-state counts and the errors seen."""

    indexed: int = 0
    failed: int = 0
    skipped: int = 0  # stale rows whose entity was gone
    errors: list[str] = field(default_factory=list)


class _Stores:
    """The external clients and embedder a drain writes through."""

    def __init__(
        self,
        *,
        os_client: Any,
        q_client: Any,
        embedder: Embedder,
        vault_path: str,
    ) -> None:
        self.os = os_client
        self.q = q_client
        self.embedder = embedder
        self.vault_path = vault_path


def _load_page(conn: psycopg.Connection, page_id: str, vault_path: str):
    """A page's ``wiki_pages`` row, its topic ids, and its vault body.

    Returns ``None`` when the page row or its vault file is gone.
    """
    page = repository.get_wiki_page(conn, page_id)  # type: ignore[arg-type]
    if page is None:
        return None
    path = Path(vault_path) / page["file_path"]
    if not path.is_file():
        return None
    body = parse_markdown(path.read_text(encoding="utf-8")).body
    topic_ids = repository.get_page_topic_ids(conn, page_id)
    return page, topic_ids, body


def _write_one(conn: psycopg.Connection, stores: _Stores, row: dict[str, Any]) -> str:
    """Project and write one entity to its index. Returns ``indexed``/``skipped``."""
    index_kind = row["index_kind"]
    entity_id = str(row["entity_id"])

    if index_kind in _PAGE_KINDS:
        loaded = _load_page(conn, entity_id, stores.vault_path)
        if loaded is None:
            return "skipped"
        page, topic_ids, body = loaded
        if index_kind == "opensearch_pages":
            doc = documents.page_document(page, body=body, topic_ids=topic_ids)
            opensearch.index_document(stores.os, opensearch.PAGES_INDEX, entity_id, doc)
        else:
            payload = documents.page_payload(page, topic_ids=topic_ids)
            vector = stores.embedder.embed(
                [documents.page_embed_text(page["title"], body)]
            )[0]
            qdrant.upsert_point(
                stores.q, qdrant.PAGES_COLLECTION, entity_id, vector, payload
            )
        return "indexed"

    chunk = repository.get_chunk_for_index(conn, entity_id)
    if chunk is None:
        return "skipped"
    if index_kind == "opensearch_chunks":
        doc = documents.chunk_document(chunk)
        opensearch.index_document(stores.os, opensearch.CHUNKS_INDEX, entity_id, doc)
    else:
        payload = documents.chunk_payload(chunk)
        vector = stores.embedder.embed([documents.chunk_embed_text(chunk["body"])])[0]
        qdrant.upsert_point(
            stores.q, qdrant.CHUNKS_COLLECTION, entity_id, vector, payload
        )
    return "indexed"


def _drain(
    conn: psycopg.Connection,
    stores: _Stores,
    *,
    index_kinds: tuple[str, ...] | None = None,
) -> SyncReport:
    """Process every matching pending row, committing each independently."""
    report = SyncReport()
    rows = repository.claim_pending_sync_rows(conn, index_kinds=index_kinds)
    for row in rows:
        try:
            outcome = _write_one(conn, stores, row)
        except Exception as exc:  # external write or load failed
            conn.rollback()
            repository.mark_sync_failed(conn, row["id"], repr(exc))
            conn.commit()
            report.failed += 1
            report.errors.append(f"{row['index_kind']} {row['entity_id']}: {exc!r}")
            continue
        if outcome == "skipped":
            repository.delete_sync_row(conn, row["id"])
            conn.commit()
            report.skipped += 1
        else:
            repository.mark_sync_indexed(conn, row["id"])
            conn.commit()
            report.indexed += 1
    return report


def _stores(vault_path: str) -> _Stores:
    return _Stores(
        os_client=opensearch_client(),
        q_client=qdrant_client(),
        embedder=get_embedder(),
        vault_path=vault_path,
    )


def sync_pending(index_kinds: tuple[str, ...] | None = None) -> SyncReport:
    """Drain the pending queue into both stores (``compendium index sync``)."""
    config = load_config()
    stores = _stores(config.vault_path)
    with connection() as conn:
        return _drain(conn, stores, index_kinds=index_kinds)


def reindex(target: str) -> SyncReport:
    """Drop the target schemas, re-enqueue every entity, and drain from empty.

    ``target`` is ``pages``, ``chunks``, or ``all``. This is the deterministic
    rebuild path: OpenSearch is byte-stable; Qdrant top-K is stable within a
    small Jaccard distance because its HNSW graph is not byte-deterministic.
    """
    if target not in _TARGET_KINDS:
        raise ValueError(f"unknown reindex target: {target}")
    config = load_config()
    stores = _stores(config.vault_path)

    if target in ("pages", "all"):
        opensearch.recreate_index(stores.os, opensearch.PAGES_INDEX)
        qdrant.recreate_collection(stores.q, qdrant.PAGES_COLLECTION)
    if target in ("chunks", "all"):
        opensearch.recreate_index(stores.os, opensearch.CHUNKS_INDEX)
        qdrant.recreate_collection(stores.q, qdrant.CHUNKS_COLLECTION)

    with connection() as conn:
        if target in ("pages", "all"):
            for page_id in repository.all_wiki_page_ids(conn):
                repository.enqueue_index(
                    conn, entity_kind="page", entity_id=page_id,
                    index_kinds=_PAGE_KINDS,
                )
        if target in ("chunks", "all"):
            for chunk_id in repository.all_chunk_ids(conn):
                repository.enqueue_index(
                    conn, entity_kind="chunk", entity_id=chunk_id,
                    index_kinds=_CHUNK_KINDS,
                )
        conn.commit()
        return _drain(conn, stores, index_kinds=_TARGET_KINDS[target])
