"""Raw-SQL data access for the operational tables.

No ORM: queries are plain SQL over psycopg 3, which adapts JSONB, arrays,
UUID, and timestamps directly. Enum-typed columns are cast explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Json

# --- sources ---------------------------------------------------------------


def insert_source(
    conn: psycopg.Connection,
    *,
    kind: str,
    title: str,
    content_hash: str,
    author: str | None = None,
    year: int | None = None,
    url: str | None = None,
    identifier: str | None = None,
    metadata: dict[str, Any] | None = None,
    inspection_status: str | None = None,
    inspection_notes: str | None = None,
) -> UUID:
    """Insert a row into ``sources`` and return its id."""
    row = conn.execute(
        """
        INSERT INTO sources (
            kind, title, content_hash, author, year, url, identifier,
            metadata, inspection_status, inspection_notes
        )
        VALUES (
            %(kind)s::source_kind, %(title)s, %(content_hash)s, %(author)s,
            %(year)s, %(url)s, %(identifier)s, %(metadata)s,
            %(inspection_status)s::inspection_status, %(inspection_notes)s
        )
        RETURNING id
        """,
        {
            "kind": kind,
            "title": title,
            "content_hash": content_hash,
            "author": author,
            "year": year,
            "url": url,
            "identifier": identifier,
            "metadata": Json(metadata if metadata is not None else {}),
            "inspection_status": inspection_status,
            "inspection_notes": inspection_notes,
        },
    ).fetchone()
    assert row is not None
    return row["id"]


def update_source(
    conn: psycopg.Connection,
    source_id: UUID,
    *,
    content_hash: str,
    title: str,
    metadata: dict[str, Any],
    inspection_status: str,
    inspection_notes: str,
) -> None:
    """Update a changed source in place (keeps its id)."""
    conn.execute(
        """
        UPDATE sources
        SET content_hash = %(content_hash)s,
            title = %(title)s,
            metadata = %(metadata)s,
            inspection_status = %(inspection_status)s::inspection_status,
            inspection_notes = %(inspection_notes)s,
            ingested_at = now()
        WHERE id = %(id)s
        """,
        {
            "id": source_id,
            "content_hash": content_hash,
            "title": title,
            "metadata": Json(metadata),
            "inspection_status": inspection_status,
            "inspection_notes": inspection_notes,
        },
    )


def get_source(conn: psycopg.Connection, source_id: UUID) -> dict[str, Any] | None:
    """Read a ``sources`` row by id, or None if absent."""
    return conn.execute(
        "SELECT * FROM sources WHERE id = %s", (source_id,)
    ).fetchone()


def get_source_by_content_hash(
    conn: psycopg.Connection, content_hash: str
) -> dict[str, Any] | None:
    """Read a ``sources`` row by content hash, or None if absent."""
    return conn.execute(
        "SELECT * FROM sources WHERE content_hash = %s", (content_hash,)
    ).fetchone()


def get_source_id_by_document_path(
    conn: psycopg.Connection, path: str
) -> UUID | None:
    """The id of the source whose document is at ``path``, or None."""
    row = conn.execute(
        "SELECT source_id FROM source_documents WHERE path = %s LIMIT 1",
        (path,),
    ).fetchone()
    return row["source_id"] if row else None


# --- source documents ------------------------------------------------------


def insert_source_document(
    conn: psycopg.Connection,
    *,
    source_id: UUID,
    path: str,
    mime_type: str,
    byte_size: int,
) -> UUID:
    """Insert a row into ``source_documents`` and return its id."""
    row = conn.execute(
        """
        INSERT INTO source_documents (source_id, path, mime_type, byte_size)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (source_id, path, mime_type, byte_size),
    ).fetchone()
    assert row is not None
    return row["id"]


def delete_source_documents(conn: psycopg.Connection, source_id: UUID) -> None:
    """Delete every ``source_documents`` row for a source."""
    conn.execute("DELETE FROM source_documents WHERE source_id = %s", (source_id,))


# --- chunks ----------------------------------------------------------------


def insert_chunks(
    conn: psycopg.Connection, source_id: UUID, chunks: Iterable[Any]
) -> int:
    """Insert chunks for a source. Each chunk exposes position,
    parent_section, body, body_hash, and token_count. Returns the count.
    """
    rows = [
        (
            source_id,
            chunk.position,
            chunk.parent_section,
            chunk.body,
            chunk.body_hash,
            chunk.token_count,
        )
        for chunk in chunks
    ]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks (
                source_id, position, parent_section, body, body_hash,
                token_count
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def delete_chunks(conn: psycopg.Connection, source_id: UUID) -> None:
    """Delete every chunk of a source."""
    conn.execute("DELETE FROM chunks WHERE source_id = %s", (source_id,))


def count_chunks(conn: psycopg.Connection, source_id: UUID) -> int:
    """Number of chunks stored for a source."""
    row = conn.execute(
        "SELECT count(*) AS n FROM chunks WHERE source_id = %s", (source_id,)
    ).fetchone()
    assert row is not None
    return row["n"]


def get_chunks_for_source(
    conn: psycopg.Connection, source_id: str | UUID
) -> list[dict[str, Any]]:
    """Every chunk of a source, ordered by position."""
    return conn.execute(
        "SELECT * FROM chunks WHERE source_id = %s ORDER BY position",
        (str(source_id),),
    ).fetchall()


def all_chunk_ids_for_source(
    conn: psycopg.Connection, source_id: str | UUID
) -> list[UUID]:
    """Ids of a source's chunks, ordered by position."""
    return [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM chunks WHERE source_id = %s ORDER BY position",
            (str(source_id),),
        )
    ]


def sources_without_page(conn: psycopg.Connection) -> list[UUID]:
    """Ids of sources that have chunks but no ``source`` page yet."""
    return [
        row["source_id"]
        for row in conn.execute(
            """
            SELECT DISTINCT c.source_id
            FROM chunks c
            WHERE NOT EXISTS (
                SELECT 1 FROM wiki_pages w
                WHERE w.source_id = c.source_id AND w.kind = 'source'
            )
            """
        )
    ]


def search_chunks(
    conn: psycopg.Connection, terms: list[str], limit: int
) -> list[dict[str, Any]]:
    """Chunks whose body matches any term (case-insensitive), with source title.

    A naive pre-retrieval lexical match used by Phase 3 synthesis.
    """
    if not terms:
        return []
    clause = " OR ".join("c.body ILIKE %s" for _ in terms)
    params = [f"%{t}%" for t in terms]
    params.append(limit)
    return conn.execute(
        f"""
        SELECT c.id, c.source_id, c.position, c.parent_section, c.body,
               s.title AS source_title
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE {clause}
        ORDER BY c.source_id, c.position
        LIMIT %s
        """,
        params,
    ).fetchall()


# --- wiki pages ------------------------------------------------------------


def insert_wiki_page(
    conn: psycopg.Connection,
    *,
    kind: str,
    slug: str,
    title: str,
    file_path: str,
    content_hash: str,
    page_id: str | UUID | None = None,
    status: str = "draft",
    corpus_revision: str | None = None,
    aliases: list[str] | None = None,
    parent_topic_id: str | UUID | None = None,
    source_id: str | UUID | None = None,
    source_kind: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    inspection_status: str | None = None,
) -> UUID:
    """Insert a row into ``wiki_pages`` and return its id."""
    row = conn.execute(
        """
        INSERT INTO wiki_pages (
            id, kind, slug, title, file_path, content_hash, status,
            corpus_revision, aliases, parent_topic_id, source_id,
            source_kind, source_metadata, inspection_status
        )
        VALUES (
            COALESCE(%(id)s::uuid, gen_random_uuid()),
            %(kind)s::page_kind, %(slug)s, %(title)s, %(file_path)s,
            %(content_hash)s, %(status)s::page_status, %(corpus_revision)s,
            %(aliases)s::text[], %(parent_topic_id)s::uuid,
            %(source_id)s::uuid, %(source_kind)s::source_kind,
            %(source_metadata)s, %(inspection_status)s::inspection_status
        )
        RETURNING id
        """,
        {
            "id": str(page_id) if page_id else None,
            "kind": kind,
            "slug": slug,
            "title": title,
            "file_path": file_path,
            "content_hash": content_hash,
            "status": status,
            "corpus_revision": corpus_revision,
            "aliases": aliases if aliases is not None else [],
            "parent_topic_id": str(parent_topic_id) if parent_topic_id else None,
            "source_id": str(source_id) if source_id else None,
            "source_kind": source_kind,
            "source_metadata": (
                Json(source_metadata) if source_metadata is not None else None
            ),
            "inspection_status": inspection_status,
        },
    ).fetchone()
    assert row is not None
    return row["id"]


def update_wiki_page(
    conn: psycopg.Connection,
    page_id: str | UUID,
    *,
    slug: str,
    title: str,
    file_path: str,
    content_hash: str,
    status: str,
    corpus_revision: str | None = None,
    aliases: list[str] | None = None,
    parent_topic_id: str | UUID | None = None,
    source_id: str | UUID | None = None,
    source_kind: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    inspection_status: str | None = None,
) -> None:
    """Update an existing ``wiki_pages`` row in place."""
    conn.execute(
        """
        UPDATE wiki_pages SET
            slug = %(slug)s,
            title = %(title)s,
            file_path = %(file_path)s,
            content_hash = %(content_hash)s,
            status = %(status)s::page_status,
            corpus_revision = %(corpus_revision)s,
            aliases = %(aliases)s::text[],
            parent_topic_id = %(parent_topic_id)s::uuid,
            source_id = %(source_id)s::uuid,
            source_kind = %(source_kind)s::source_kind,
            source_metadata = %(source_metadata)s,
            inspection_status = %(inspection_status)s::inspection_status,
            updated_at = now()
        WHERE id = %(id)s
        """,
        {
            "id": str(page_id),
            "slug": slug,
            "title": title,
            "file_path": file_path,
            "content_hash": content_hash,
            "status": status,
            "corpus_revision": corpus_revision,
            "aliases": aliases if aliases is not None else [],
            "parent_topic_id": str(parent_topic_id) if parent_topic_id else None,
            "source_id": str(source_id) if source_id else None,
            "source_kind": source_kind,
            "source_metadata": (
                Json(source_metadata) if source_metadata is not None else None
            ),
            "inspection_status": inspection_status,
        },
    )


def get_wiki_page(conn: psycopg.Connection, page_id: UUID) -> dict[str, Any] | None:
    """Read a ``wiki_pages`` row by id, or None if absent."""
    return conn.execute(
        "SELECT * FROM wiki_pages WHERE id = %s", (page_id,)
    ).fetchone()


def get_wiki_page_by_slug(
    conn: psycopg.Connection, kind: str, slug: str
) -> dict[str, Any] | None:
    """Read a ``wiki_pages`` row by kind and slug, or None."""
    return conn.execute(
        "SELECT * FROM wiki_pages WHERE kind = %s::page_kind AND slug = %s",
        (kind, slug),
    ).fetchone()


def get_wiki_page_by_source_id(
    conn: psycopg.Connection, source_id: str | UUID
) -> dict[str, Any] | None:
    """Read the ``source`` page for a given source, or None."""
    return conn.execute(
        "SELECT * FROM wiki_pages WHERE source_id = %s", (str(source_id),)
    ).fetchone()


def existing_slugs(conn: psycopg.Connection, kind: str) -> set[str]:
    """Every slug already used by a page of the given kind."""
    return {
        row["slug"]
        for row in conn.execute(
            "SELECT slug FROM wiki_pages WHERE kind = %s::page_kind", (kind,)
        )
    }


def insert_wiki_page_revision(
    conn: psycopg.Connection,
    *,
    page_id: str | UUID,
    body: str,
    content_hash: str,
    frontmatter: dict[str, Any],
    generator: str,
    notes: str | None = None,
) -> UUID:
    """Insert a ``wiki_page_revisions`` snapshot and return its id."""
    row = conn.execute(
        """
        INSERT INTO wiki_page_revisions (
            page_id, body, content_hash, frontmatter, generator, notes
        )
        VALUES (%s, %s, %s, %s, %s::page_generator, %s)
        RETURNING id
        """,
        (page_id, body, content_hash, Json(frontmatter), generator, notes),
    ).fetchone()
    assert row is not None
    return row["id"]


def set_current_revision(
    conn: psycopg.Connection, page_id: str | UUID, revision_id: str | UUID
) -> None:
    """Point a page at its current revision."""
    conn.execute(
        "UPDATE wiki_pages SET current_revision_id = %s WHERE id = %s",
        (revision_id, page_id),
    )


def set_page_topics(
    conn: psycopg.Connection, page_id: str | UUID, topic_ids: Iterable[str]
) -> None:
    """Replace a concept page's topic membership."""
    conn.execute("DELETE FROM wiki_pages_topics WHERE page_id = %s", (page_id,))
    for topic_id in topic_ids:
        conn.execute(
            "INSERT INTO wiki_pages_topics (page_id, topic_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (page_id, topic_id),
        )


# --- index sync state ------------------------------------------------------


def enqueue_index(
    conn: psycopg.Connection,
    *,
    entity_kind: str,
    entity_id: str | UUID,
    index_kinds: Iterable[str],
) -> None:
    """Mark an entity ``pending`` for each named index.

    Idempotent via the ``(entity_kind, entity_id, index_kind)`` unique
    constraint: re-enqueuing an already-``indexed`` entity resets its rows to
    ``pending`` and clears the prior error and attempt count.
    """
    for index_kind in index_kinds:
        conn.execute(
            """
            INSERT INTO index_sync_state (entity_kind, entity_id, index_kind)
            VALUES (%s, %s, %s::index_kind)
            ON CONFLICT (entity_kind, entity_id, index_kind)
            DO UPDATE SET state = 'pending', attempts = 0,
                          last_error = NULL, updated_at = now()
            """,
            (entity_kind, str(entity_id), index_kind),
        )


def dequeue_chunks_for_source(conn: psycopg.Connection, source_id: str | UUID) -> None:
    """Drop the sync rows of a source's chunks (before the chunks are deleted)."""
    conn.execute(
        """
        DELETE FROM index_sync_state
        WHERE entity_kind = 'chunk'
          AND entity_id IN (SELECT id FROM chunks WHERE source_id = %s)
        """,
        (str(source_id),),
    )


def claim_pending_sync_rows(
    conn: psycopg.Connection,
    limit: int | None = None,
    index_kinds: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Pending sync rows in id order (backed by the partial pending index)."""
    sql = (
        "SELECT id, entity_kind, entity_id, index_kind, attempts "
        "FROM index_sync_state WHERE state = 'pending'"
    )
    params: list[Any] = []
    if index_kinds is not None:
        kinds = list(index_kinds)
        sql += " AND index_kind = ANY(%s::index_kind[])"
        params.append(kinds)
    sql += " ORDER BY id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def mark_sync_indexed(conn: psycopg.Connection, row_id: int) -> None:
    """Flip a sync row to ``indexed``, clearing any prior error."""
    conn.execute(
        """
        UPDATE index_sync_state
        SET state = 'indexed', attempts = attempts + 1,
            last_error = NULL, updated_at = now()
        WHERE id = %s
        """,
        (row_id,),
    )


def mark_sync_failed(conn: psycopg.Connection, row_id: int, error: str) -> None:
    """Flip a sync row to ``failed``, recording the error and bumping attempts."""
    conn.execute(
        """
        UPDATE index_sync_state
        SET state = 'failed', attempts = attempts + 1,
            last_error = %s, updated_at = now()
        WHERE id = %s
        """,
        (error[:2000], row_id),
    )


def delete_sync_row(conn: psycopg.Connection, row_id: int) -> None:
    """Drop a sync row whose entity no longer exists (stale after re-ingest)."""
    conn.execute("DELETE FROM index_sync_state WHERE id = %s", (row_id,))


def sync_lag(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """The ``index_kind`` / ``state`` / count breakdown from ``v_sync_lag``."""
    return conn.execute(
        "SELECT index_kind, state, n FROM v_sync_lag ORDER BY index_kind, state"
    ).fetchall()


# --- index entity loaders --------------------------------------------------


def get_page_topic_ids(conn: psycopg.Connection, page_id: str | UUID) -> list[str]:
    """Topic ids a concept page belongs to, via ``wiki_pages_topics``."""
    return [
        str(row["topic_id"])
        for row in conn.execute(
            "SELECT topic_id FROM wiki_pages_topics WHERE page_id = %s",
            (str(page_id),),
        )
    ]


def get_chunk_for_index(
    conn: psycopg.Connection, chunk_id: str | UUID
) -> dict[str, Any] | None:
    """A chunk row joined to its source's title and kind, or None if gone."""
    return conn.execute(
        """
        SELECT c.id, c.source_id, c.position, c.parent_section, c.body,
               c.token_count, c.created_at,
               s.title AS source_title, s.kind AS source_kind
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE c.id = %s
        """,
        (str(chunk_id),),
    ).fetchone()


def all_wiki_page_ids(conn: psycopg.Connection) -> list[UUID]:
    """Every wiki page id, in insertion order."""
    return [row["id"] for row in conn.execute("SELECT id FROM wiki_pages ORDER BY id")]


def all_chunk_ids(conn: psycopg.Connection) -> list[UUID]:
    """Every chunk id, in insertion order."""
    return [row["id"] for row in conn.execute("SELECT id FROM chunks ORDER BY id")]


def all_source_ids(conn: psycopg.Connection) -> list[UUID]:
    """Every source id, in insertion order."""
    return [row["id"] for row in conn.execute("SELECT id FROM sources ORDER BY id")]


# --- query traces ----------------------------------------------------------


def insert_query_trace(
    conn: psycopg.Connection,
    *,
    query_text: str,
    embedding_model: str,
    query_embedding: list[float] | None,
    pipeline: dict[str, Any],
    final_ranking: list[dict[str, Any]],
    latencies_ms: dict[str, Any],
    coverage_score: float | None,
    fallback_to_chunks: bool,
    gaps: list[dict[str, Any]],
    corpus_revision: str | None = None,
    graph_expansion: dict[str, Any] | None = None,
) -> UUID:
    """Insert one ``query_traces`` row and return its id.

    ``query_embedding`` is stored as ``REAL[]`` (pgvector deferred); the JSONB
    columns are adapted with ``Json``. Every query writes exactly one trace,
    regardless of outcome.
    """
    row = conn.execute(
        """
        INSERT INTO query_traces (
            corpus_revision, query_text, embedding_model, query_embedding,
            pipeline, final_ranking, latencies_ms, coverage_score,
            fallback_to_chunks, gaps, graph_expansion
        )
        VALUES (
            %s, %s, %s, %s::real[],
            %s, %s, %s, %s,
            %s, %s, %s
        )
        RETURNING id
        """,
        (
            corpus_revision,
            query_text,
            embedding_model,
            query_embedding,
            Json(pipeline),
            Json(final_ranking),
            Json(latencies_ms),
            coverage_score,
            fallback_to_chunks,
            Json(gaps),
            Json(graph_expansion) if graph_expansion is not None else None,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def ensure_corpus_revision(conn: psycopg.Connection) -> str:
    """Return the current corpus revision id, creating one if none exists."""
    row = conn.execute(
        "SELECT id FROM corpus_revisions ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if row is not None:
        return row["id"]
    revision_id = "rev-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    conn.execute(
        "INSERT INTO corpus_revisions (id, description) VALUES (%s, %s)",
        (revision_id, "auto-created on first page write"),
    )
    return revision_id
