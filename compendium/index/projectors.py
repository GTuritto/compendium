"""One seam for projecting a PostgreSQL entity into a derived store.

Each derived store is a ``StoreProjector`` adapter that owns both halves of its
projection: mapping an entity (a ``wiki_pages`` row plus the vault body, or a
``chunks`` row) into the store's shape, and writing it. The sync drain
dispatches a pending ``index_sync_state`` row to the adapter registered for its
``index_kind`` (see :data:`PROJECTORS`) instead of branching per store inline.

Each adapter callable takes ``(conn, stores, row)`` and returns ``"indexed"``
or ``"skipped"`` (the latter when the entity has since been deleted). ``stores``
is duck-typed: it exposes ``os``, ``q``, ``embedder``, ``graph``, and
``vault_path`` (the sync module's ``_Stores``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from compendium.db import repository
from compendium.graph import projection
from compendium.index import documents, opensearch, qdrant
from compendium.wiki.page import parse_markdown


def load_page(conn: psycopg.Connection, page_id: str, vault_path: str):
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


class OpenSearchProjector:
    """Projects pages and chunks into the OpenSearch (BM25) indexes."""

    def write_page(self, conn: psycopg.Connection, stores: Any, row: dict[str, Any]) -> str:
        entity_id = str(row["entity_id"])
        loaded = load_page(conn, entity_id, stores.vault_path)
        if loaded is None:
            return "skipped"
        page, topic_ids, body = loaded
        doc = documents.page_document(page, body=body, topic_ids=topic_ids)
        opensearch.index_document(stores.os, opensearch.PAGES_INDEX, entity_id, doc)
        return "indexed"

    def write_chunk(self, conn: psycopg.Connection, stores: Any, row: dict[str, Any]) -> str:
        entity_id = str(row["entity_id"])
        chunk = repository.get_chunk_for_index(conn, entity_id)
        if chunk is None:
            return "skipped"
        doc = documents.chunk_document(chunk)
        opensearch.index_document(stores.os, opensearch.CHUNKS_INDEX, entity_id, doc)
        return "indexed"


class QdrantProjector:
    """Projects pages and chunks into the Qdrant (dense vector) collections."""

    def write_page(self, conn: psycopg.Connection, stores: Any, row: dict[str, Any]) -> str:
        entity_id = str(row["entity_id"])
        loaded = load_page(conn, entity_id, stores.vault_path)
        if loaded is None:
            return "skipped"
        page, topic_ids, body = loaded
        payload = documents.page_payload(page, topic_ids=topic_ids)
        vector = stores.embedder.embed([documents.page_embed_text(page["title"], body)])[0]
        qdrant.upsert_point(stores.q, qdrant.PAGES_COLLECTION, entity_id, vector, payload)
        return "indexed"

    def write_chunk(self, conn: psycopg.Connection, stores: Any, row: dict[str, Any]) -> str:
        entity_id = str(row["entity_id"])
        chunk = repository.get_chunk_for_index(conn, entity_id)
        if chunk is None:
            return "skipped"
        payload = documents.chunk_payload(chunk)
        vector = stores.embedder.embed([documents.chunk_embed_text(chunk["body"])])[0]
        qdrant.upsert_point(stores.q, qdrant.CHUNKS_COLLECTION, entity_id, vector, payload)
        return "indexed"


class MemgraphProjector:
    """Projects pages and chunks into the Memgraph structural index.

    Delegates to :mod:`compendium.graph.projection`, which builds the typed
    nodes and the automatic ``PART_OF``/``EVIDENCES``/``GROUNDS`` edges.
    """

    def write(self, conn: psycopg.Connection, stores: Any, row: dict[str, Any]) -> str:
        entity_id = str(row["entity_id"])
        if row["entity_kind"] == "page":
            ok = projection.project_page(stores.graph, conn, entity_id, stores.vault_path)
        else:
            ok = projection.project_chunk(stores.graph, conn, entity_id)
        return "indexed" if ok else "skipped"


_os = OpenSearchProjector()
_qd = QdrantProjector()
_mg = MemgraphProjector()

# index_kind -> a callable (conn, stores, row) -> "indexed" | "skipped".
PROJECTORS = {
    "opensearch_pages": _os.write_page,
    "opensearch_chunks": _os.write_chunk,
    "qdrant_pages": _qd.write_page,
    "qdrant_chunks": _qd.write_chunk,
    "memgraph": _mg.write,
}
