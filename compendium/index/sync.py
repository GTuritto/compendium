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
from typing import Any

import psycopg

from compendium.config import load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.graph.client import graph_driver
from compendium.index import opensearch, projectors, qdrant
from compendium.index.clients import (
    opensearch_client,
    opensearch_reachable,
    qdrant_client,
    qdrant_reachable,
)
from compendium.profiling import timed
from compendium.index.embedder import Embedder, get_embedder

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


@dataclass
class IndexStatusReport:
    """Derived-index counts and sync-queue lag.

    ``opensearch`` and ``qdrant`` map index/collection name to document count,
    or are ``None`` when that store is unreachable. ``sync_lag`` is the rows of
    the ``v_sync_lag`` view (one per index_kind/state).
    """

    opensearch: dict[str, int] | None = None
    qdrant: dict[str, int] | None = None
    sync_lag: list[dict[str, Any]] = field(default_factory=list)


class _Stores:
    """The external clients and embedder a drain writes through."""

    def __init__(
        self,
        *,
        os_client: Any,
        q_client: Any,
        embedder: Embedder,
        vault_path: str,
        graph: Any = None,
    ) -> None:
        self.os = os_client
        self.q = q_client
        self.embedder = embedder
        self.vault_path = vault_path
        self.graph = graph  # Bolt driver, lazily connected; used by the memgraph kind


def _write_one(conn: psycopg.Connection, stores: _Stores, row: dict[str, Any]) -> str:
    """Dispatch one pending row to its store's projector. ``indexed``/``skipped``."""
    return projectors.PROJECTORS[row["index_kind"]](conn, stores, row)


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
            with timed("index.write", index_kind=row["index_kind"]):
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
        graph=graph_driver(),  # lazy: connects only when a memgraph row is drained
    )


def sync_pending(index_kinds: tuple[str, ...] | None = None) -> SyncReport:
    """Drain the pending queue into the derived stores (``compendium index sync``)."""
    config = load_config()
    stores = _stores(config.vault_path)
    try:
        with connection() as conn:
            return _drain(conn, stores, index_kinds=index_kinds)
    finally:
        stores.graph.close()


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
    try:
        return _reindex(target, stores)
    finally:
        stores.graph.close()


def status() -> IndexStatusReport:
    """Counts per index/collection (or unreachable), plus sync-queue lag.

    Owns client construction and reachability so callers render a report rather
    than wiring stores themselves.
    """
    report = IndexStatusReport()

    os_client = opensearch_client()
    if opensearch_reachable(os_client):
        report.opensearch = {
            index: opensearch.count(os_client, index)
            for index in (opensearch.PAGES_INDEX, opensearch.CHUNKS_INDEX)
        }

    q_client = qdrant_client()
    if qdrant_reachable(q_client):
        report.qdrant = {
            collection: qdrant.count(q_client, collection)
            for collection in (qdrant.PAGES_COLLECTION, qdrant.CHUNKS_COLLECTION)
        }

    with connection() as conn:
        report.sync_lag = list(repository.sync_lag(conn))
    return report


def _reindex(target: str, stores: _Stores) -> SyncReport:
    # v0.2 Phase 5: regenerate the OpenSearch synonym list from the current
    # page aliases. The lines feed the analyzer's inline `synonym` filter
    # so a re-dropped vault picks up new aliases on reindex.
    from compendium.index.synonyms import generate_synonyms

    with connection() as conn:
        synonyms = generate_synonyms(conn)

    if target in ("pages", "all"):
        opensearch.recreate_index(stores.os, opensearch.PAGES_INDEX, synonyms=synonyms)
        qdrant.recreate_collection(stores.q, qdrant.PAGES_COLLECTION)
    if target in ("chunks", "all"):
        opensearch.recreate_index(stores.os, opensearch.CHUNKS_INDEX, synonyms=synonyms)
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
