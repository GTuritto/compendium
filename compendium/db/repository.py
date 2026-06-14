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


def source_page_slugs_for_chunks(
    conn: psycopg.Connection, chunk_ids: list[str]
) -> dict[str, str]:
    """Map each chunk id to its parent source page's slug (v0.4 Phase 1).

    The chunk-arm scorer reduces a chunk hit to its parent source page so both
    arms score in page space (ADR-016). Chunks whose source has no source page
    are omitted. One batched join; reader for ``compendium/validate/`` only.
    """
    if not chunk_ids:
        return {}
    rows = conn.execute(
        """
        SELECT c.id AS chunk_id, w.slug AS slug
        FROM chunks c
        JOIN wiki_pages w ON w.source_id = c.source_id AND w.kind = 'source'
        WHERE c.id = ANY(%s)
        """,
        ([str(cid) for cid in chunk_ids],),
    ).fetchall()
    return {str(r["chunk_id"]): r["slug"] for r in rows}


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


def pages_changed_since(
    conn: psycopg.Connection, since: Any | None
) -> list[dict[str, Any]]:
    """Concept + source pages whose current revision is newer than ``since``.

    The change-detection scope for the v0.2 Phase 8 edge extractor. When
    ``since`` is None (cold start / full sweep), every concept and source page is
    returned. Each row carries ``id, kind, slug, title, source_id,
    current_revision_id`` so the extractor can resolve the graph node and stamp
    ``source_revision_id`` provenance.
    """
    cols = "w.id, w.kind, w.slug, w.title, w.source_id, w.current_revision_id"
    if since is None:
        return conn.execute(
            f"SELECT {cols} FROM wiki_pages w "
            "WHERE w.kind IN ('concept', 'source') "
            "ORDER BY w.created_at",
        ).fetchall()
    return conn.execute(
        f"SELECT {cols} FROM wiki_pages w "
        "JOIN wiki_page_revisions r ON r.id = w.current_revision_id "
        "WHERE w.kind IN ('concept', 'source') AND r.created_at > %s "
        "ORDER BY r.created_at",
        (since,),
    ).fetchall()


def list_wiki_pages(
    conn: psycopg.Connection,
    *,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Filtered wiki-page list for the access surface (v0.2 Phase 7).

    Newest first. ``kind`` and ``status`` are optional equality filters cast to
    their enum types; ``limit`` bounds the result.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if kind is not None:
        clauses.append("kind = %s::page_kind")
        params.append(kind)
    if status is not None:
        clauses.append("status = %s::page_status")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    return conn.execute(
        "SELECT id, kind, slug, title, status, file_path, created_at "
        f"FROM wiki_pages{where} ORDER BY created_at DESC, slug ASC LIMIT %s",
        params,
    ).fetchall()


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


# --- telemetry reads (Phase 7) ---------------------------------------------


def get_query_trace(conn: psycopg.Connection, trace_id: str | UUID) -> dict[str, Any] | None:
    """A single ``query_traces`` row by id, or None."""
    return conn.execute(
        "SELECT * FROM query_traces WHERE id = %s", (str(trace_id),)
    ).fetchone()


def list_query_traces(conn: psycopg.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """Recent traces, newest first."""
    return conn.execute(
        "SELECT id, query_text, coverage_score, fallback_to_chunks, "
        "jsonb_array_length(gaps) AS gap_count, created_at "
        "FROM query_traces ORDER BY created_at DESC LIMIT %s",
        (limit,),
    ).fetchall()


# --- ask traces (v0.2 Phase 6) ---------------------------------------------


def insert_ask_trace(
    conn: psycopg.Connection,
    *,
    query_trace_id: str | UUID,
    prompt_template_id: str,
    model: str,
    endpoint: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_estimate: float | None,
    answer_text: str | None,
    refused: bool,
) -> UUID:
    """Insert one ``ask_traces`` row and return its id.

    Joined to the ``query_traces`` row produced by the retrieval via
    ``query_trace_id``. A refusal still writes a row (``refused=true``,
    ``answer_text`` null). Every ``compendium ask`` writes exactly one row.
    """
    row = conn.execute(
        """
        INSERT INTO ask_traces (
            query_trace_id, prompt_template_id, model, endpoint,
            input_tokens, output_tokens, cost_estimate, answer_text, refused
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            str(query_trace_id),
            prompt_template_id,
            model,
            endpoint,
            input_tokens,
            output_tokens,
            cost_estimate,
            answer_text,
            refused,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def get_ask_trace(conn: psycopg.Connection, ask_trace_id: str | UUID) -> dict[str, Any] | None:
    """A single ``ask_traces`` row by id, or None."""
    return conn.execute(
        "SELECT * FROM ask_traces WHERE id = %s", (str(ask_trace_id),)
    ).fetchone()


def distinct_ask_questions(
    conn: psycopg.Connection, limit: int = 200
) -> list[dict[str, Any]]:
    """Distinct real questions asked, newest first (v0.4 Phase 1 harvest).

    Joins ``ask_traces`` to ``query_traces`` for the question text; collapses
    repeats to the most recent ask. Reader for ``compendium/validate/`` only.
    """
    return conn.execute(
        """
        SELECT q.query_text AS query_text, max(a.created_at) AS asked_at
        FROM ask_traces a
        JOIN query_traces q ON q.id = a.query_trace_id
        GROUP BY q.query_text
        ORDER BY asked_at DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()


def get_ask_trace_with_query(
    conn: psycopg.Connection, ask_trace_id: str | UUID
) -> dict[str, Any] | None:
    """An ``ask_traces`` row joined to its ``query_traces`` row, or None.

    The query trace's text and coverage ride alongside the ask trace under the
    ``query_text`` and ``query_coverage_score`` keys.
    """
    return conn.execute(
        """
        SELECT a.*, q.query_text AS query_text,
               q.coverage_score AS query_coverage_score
        FROM ask_traces a
        JOIN query_traces q ON q.id = a.query_trace_id
        WHERE a.id = %s
        """,
        (str(ask_trace_id),),
    ).fetchone()


def resolve_page_by_slug(
    conn: psycopg.Connection, slug: str
) -> dict[str, Any] | None:
    """A ``wiki_pages`` row by slug across kinds.

    Slugs are unique per kind, so a slug may match more than one page. Raises
    ValueError when the slug is ambiguous; returns None when nothing matches.
    """
    rows = conn.execute(
        "SELECT * FROM wiki_pages WHERE slug = %s", (slug,)
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        kinds = ", ".join(sorted(r["kind"] for r in rows))
        raise ValueError(f"slug '{slug}' is ambiguous across kinds: {kinds}")
    return rows[0]


def get_page_revisions(
    conn: psycopg.Connection, page_id: str | UUID
) -> list[dict[str, Any]]:
    """A page's revisions, oldest first (ordinal 1 = oldest)."""
    return conn.execute(
        "SELECT id, page_id, content_hash, generator, notes, created_at "
        "FROM wiki_page_revisions WHERE page_id = %s ORDER BY created_at, id",
        (str(page_id),),
    ).fetchall()


def get_revision(conn: psycopg.Connection, revision_id: str | UUID) -> dict[str, Any] | None:
    """A full ``wiki_page_revisions`` row (body + frontmatter) by id, or None."""
    return conn.execute(
        "SELECT * FROM wiki_page_revisions WHERE id = %s", (str(revision_id),)
    ).fetchone()


def record_promotion(
    conn: psycopg.Connection,
    *,
    page_id: str | UUID,
    kind: str,
    from_revision_id: str | UUID | None,
    to_revision_id: str | UUID | None,
    related_page_ids: list[str] | None = None,
    notes: str | None = None,
) -> UUID:
    """Insert a ``promotion_events`` row and return its id."""
    row = conn.execute(
        """
        INSERT INTO promotion_events (
            page_id, kind, from_revision_id, to_revision_id,
            related_page_ids, notes
        )
        VALUES (%s, %s::promotion_kind, %s, %s, %s::uuid[], %s)
        RETURNING id
        """,
        (
            str(page_id),
            kind,
            str(from_revision_id) if from_revision_id else None,
            str(to_revision_id) if to_revision_id else None,
            [str(p) for p in (related_page_ids or [])],
            notes,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def list_promotion_events(
    conn: psycopg.Connection, slug: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Promotion events newest first, optionally filtered to one page's slug."""
    sql = (
        "SELECT pe.id, w.slug, w.kind AS page_kind, pe.kind, pe.notes, "
        "pe.created_at FROM promotion_events pe "
        "JOIN wiki_pages w ON w.id = pe.page_id"
    )
    params: list[Any] = []
    if slug is not None:
        sql += " WHERE w.slug = %s"
        params.append(slug)
    sql += " ORDER BY pe.created_at DESC LIMIT %s"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


# --- ops-console reads (Phase 8) -------------------------------------------


def table_counts(conn: psycopg.Connection) -> dict[str, int]:
    """Row counts for the entities the dashboard summarizes."""
    counts: dict[str, int] = {}
    for table in ("sources", "chunks", "wiki_pages", "query_traces", "promotion_events"):
        counts[table] = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
    return counts


def list_sources(conn: psycopg.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Sources newest first, with inspection status."""
    return conn.execute(
        "SELECT id, kind, title, inspection_status, ingested_at "
        "FROM sources ORDER BY ingested_at DESC LIMIT %s",
        (limit,),
    ).fetchall()


def list_pages(
    conn: psycopg.Connection,
    *,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Wiki pages, optionally filtered by kind and/or status, newest first."""
    sql = "SELECT id, kind, slug, title, status, updated_at FROM wiki_pages"
    clauses: list[str] = []
    params: list[Any] = []
    if kind:
        clauses.append("kind = %s::page_kind")
        params.append(kind)
    if status:
        clauses.append("status = %s::page_status")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC LIMIT %s"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def list_open_curation_signals(
    conn: psycopg.Connection, limit: int = 200
) -> list[dict[str, Any]]:
    """Open curation signals by priority (from ``v_open_curation_signals``)."""
    return conn.execute(
        "SELECT kind, priority, payload, created_at "
        "FROM v_open_curation_signals ORDER BY priority DESC, created_at DESC LIMIT %s",
        (limit,),
    ).fetchall()


# --- curation loop (Phase 9) -----------------------------------------------


def list_open_signals(
    conn: psycopg.Connection, limit: int = 200
) -> list[dict[str, Any]]:
    """Open signals (with id) by priority — for the TUI, which acts on them."""
    return conn.execute(
        "SELECT id, kind, priority, payload, status, created_at "
        "FROM graph_curation_signals WHERE status = 'open' "
        "ORDER BY priority DESC, created_at DESC LIMIT %s",
        (limit,),
    ).fetchall()


def open_analysis_run(conn: psycopg.Connection) -> UUID:
    """Open a ``graph_analysis_runs`` row and return its id."""
    row = conn.execute(
        "INSERT INTO graph_analysis_runs DEFAULT VALUES RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


def count_analysis_runs(conn: psycopg.Connection) -> int:
    """Number of ``graph_analysis_runs`` rows (drives the periodic full sweep)."""
    row = conn.execute("SELECT count(*) AS n FROM graph_analysis_runs").fetchone()
    return int(row["n"]) if row else 0


def complete_analysis_run(
    conn: psycopg.Connection, run_id: str | UUID, *, signal_count: int, summary: dict[str, Any]
) -> None:
    """Mark an analysis run complete with its signal count and summary."""
    conn.execute(
        "UPDATE graph_analysis_runs SET completed_at = now(), "
        "signal_count = %s, summary = %s WHERE id = %s",
        (signal_count, Json(summary), str(run_id)),
    )


def open_signal_keys(conn: psycopg.Connection) -> set[tuple[str, str]]:
    """(kind, dedup_key) for every currently-open signal, for dedup.

    The dedup key is a stable identifier inside the payload (``page_id`` for the
    page-keyed kinds, else the sorted query text / concept list).
    """
    keys: set[tuple[str, str]] = set()
    for row in conn.execute(
        "SELECT kind, payload FROM graph_curation_signals WHERE status = 'open'"
    ):
        keys.add((row["kind"], _signal_dedup_key(row["payload"])))
    return keys


def _signal_dedup_key(payload: dict[str, Any]) -> str:
    if payload.get("page_id"):
        return str(payload["page_id"])
    if payload.get("query_text"):
        return str(payload["query_text"])
    if payload.get("edge_id"):
        return str(payload["edge_id"])
    return str(sorted(payload.get("missing_concepts", [])))


def insert_curation_signal(
    conn: psycopg.Connection,
    *,
    kind: str,
    priority: int,
    payload: dict[str, Any],
    run_id: str | UUID | None = None,
) -> UUID:
    """Insert a ``graph_curation_signals`` row and return its id."""
    row = conn.execute(
        """
        INSERT INTO graph_curation_signals (kind, priority, payload, run_id)
        VALUES (%s::curation_signal_kind, %s, %s, %s)
        RETURNING id
        """,
        (kind, priority, Json(payload), str(run_id) if run_id else None),
    ).fetchone()
    assert row is not None
    return row["id"]


def get_curation_signal(
    conn: psycopg.Connection, signal_id: str | UUID
) -> dict[str, Any] | None:
    """A single ``graph_curation_signals`` row by id, or None."""
    return conn.execute(
        "SELECT * FROM graph_curation_signals WHERE id = %s", (str(signal_id),)
    ).fetchone()


def set_signal_status(
    conn: psycopg.Connection,
    signal_id: str | UUID,
    status: str,
    *,
    addressed_revision_id: str | UUID | None = None,
) -> None:
    """Move a signal to a new status; set the addressed revision when addressing."""
    conn.execute(
        """
        UPDATE graph_curation_signals
        SET status = %(status)s::curation_signal_status,
            addressed_revision_id = COALESCE(%(rev)s::uuid, addressed_revision_id),
            addressed_at = CASE WHEN %(status)s::text = 'addressed'
                                THEN now() ELSE addressed_at END
        WHERE id = %(id)s::uuid
        """,
        {
            "status": status,
            "rev": str(addressed_revision_id) if addressed_revision_id else None,
            "id": str(signal_id),
        },
    )


def attach_synth_page(
    conn: psycopg.Connection, signal_id: str | UUID, page_id: str | UUID, slug: str
) -> None:
    """Record on the signal which page its synth produced (for the promote hook)."""
    conn.execute(
        "UPDATE graph_curation_signals "
        "SET payload = payload || jsonb_build_object("
        "'synth_page_id', %s::text, 'synth_slug', %s::text) "
        "WHERE id = %s::uuid",
        (str(page_id), slug, str(signal_id)),
    )


def find_in_progress_signal_by_synth_slug(
    conn: psycopg.Connection, slug: str
) -> dict[str, Any] | None:
    """An in-progress signal whose synth produced the page with this slug, or None."""
    return conn.execute(
        "SELECT * FROM graph_curation_signals "
        "WHERE status = 'in_progress' AND payload->>'synth_slug' = %s LIMIT 1",
        (slug,),
    ).fetchone()


def source_ids_for_chunks(
    conn: psycopg.Connection, chunk_ids: list[str]
) -> list[str]:
    """Distinct source ids for a set of chunk ids."""
    if not chunk_ids:
        return []
    rows = conn.execute(
        "SELECT DISTINCT source_id FROM chunks WHERE id = ANY(%s::uuid[])",
        (chunk_ids,),
    ).fetchall()
    return [str(r["source_id"]) for r in rows]


def low_coverage_traces(
    conn: psycopg.Connection, threshold: float, limit: int = 500
) -> list[dict[str, Any]]:
    """Recent traces at/below the coverage threshold or that fell back to chunks."""
    return conn.execute(
        "SELECT id, query_text, coverage_score, fallback_to_chunks "
        "FROM query_traces "
        "WHERE coverage_score <= %s OR fallback_to_chunks "
        "ORDER BY created_at DESC LIMIT %s",
        (threshold, limit),
    ).fetchall()


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


# --- semantic edges (system-of-record home; arch-semantic-edge-persistence) -
#
# Semantic edges are projected into Memgraph but live here so `graph rebuild`
# can replay them (ADR-004/ADR-005: the graph is fully derived). One row per
# directed edge, keyed on the same tuple Memgraph MERGEs on. Provenance columns
# mirror the ADR-010 bag; absent keys are stored NULL. The graph stays the
# arbiter of curator-protection/canonicalisation -- these functions only mirror
# the resolved edge (see compendium/graph/semantic_edges.py).

# The provenance keys carried on a semantic edge, in column order.
_SEMANTIC_EDGE_PROVENANCE = (
    "extracted_by", "model", "confidence", "extracted_at", "source_revision_id", "weight",
)


def upsert_semantic_edge_row(
    conn: psycopg.Connection,
    *,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    provenance: dict[str, Any],
) -> None:
    """Insert or refresh the row for a directed semantic edge.

    ON CONFLICT on the directed tuple refreshes the provenance in place, so the
    table holds one row per edge -- the analog of Memgraph's MERGE.
    """
    params: dict[str, Any] = {
        "edge_type": edge_type,
        "from_label": from_label,
        "from_id": from_id,
        "to_label": to_label,
        "to_id": to_id,
    }
    for key in _SEMANTIC_EDGE_PROVENANCE:
        params[key] = provenance.get(key)
    conn.execute(
        """
        INSERT INTO semantic_edges (
            edge_type, from_label, from_id, to_label, to_id,
            extracted_by, model, confidence, extracted_at, source_revision_id, weight
        )
        VALUES (
            %(edge_type)s, %(from_label)s, %(from_id)s, %(to_label)s, %(to_id)s,
            %(extracted_by)s, %(model)s, %(confidence)s, %(extracted_at)s,
            %(source_revision_id)s, %(weight)s
        )
        ON CONFLICT (edge_type, from_label, from_id, to_label, to_id)
        DO UPDATE SET
            extracted_by = EXCLUDED.extracted_by,
            model = EXCLUDED.model,
            confidence = EXCLUDED.confidence,
            extracted_at = EXCLUDED.extracted_at,
            source_revision_id = EXCLUDED.source_revision_id,
            weight = EXCLUDED.weight
        """,
        params,
    )


def delete_semantic_edge_row(
    conn: psycopg.Connection,
    *,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
) -> None:
    """Remove the row for a directed semantic edge (idempotent)."""
    conn.execute(
        "DELETE FROM semantic_edges "
        "WHERE edge_type = %s AND from_label = %s AND from_id = %s "
        "AND to_label = %s AND to_id = %s",
        (edge_type, from_label, from_id, to_label, to_id),
    )


def all_semantic_edges(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Every persisted semantic edge, for the rebuild replay pass."""
    return conn.execute(
        "SELECT edge_type, from_label, from_id, to_label, to_id, "
        "extracted_by, model, confidence, extracted_at, source_revision_id, weight "
        "FROM semantic_edges ORDER BY edge_type, from_id, to_id"
    ).fetchall()


# --- profile stats (read-only aggregation over existing tables) -------------


def retrieval_summary_stats(conn: psycopg.Connection, days: int) -> dict[str, Any]:
    """Query count, fallback rate, and mean coverage over the window."""
    return conn.execute(
        "SELECT COUNT(*) AS n, "
        "AVG(CASE WHEN fallback_to_chunks THEN 1.0 ELSE 0.0 END) AS fallback_rate, "
        "AVG(coverage_score) AS avg_coverage "
        "FROM query_traces "
        "WHERE created_at >= now() - make_interval(days => %s)",
        (days,),
    ).fetchone()


def retrieval_stage_stats(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Per-stage avg and p95 latency from query_traces.latencies_ms."""
    return conn.execute(
        "SELECT key AS stage, COUNT(*) AS n, "
        "AVG(value::float8) AS avg_ms, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY value::float8) AS p95_ms "
        "FROM query_traces, LATERAL jsonb_each_text(latencies_ms) "
        "WHERE created_at >= now() - make_interval(days => %s) "
        "GROUP BY key ORDER BY key",
        (days,),
    ).fetchall()


def retrieval_per_day(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Daily query throughput over the window."""
    return conn.execute(
        "SELECT date_trunc('day', created_at)::date AS day, COUNT(*) AS n "
        "FROM query_traces "
        "WHERE created_at >= now() - make_interval(days => %s) "
        "GROUP BY 1 ORDER BY 1",
        (days,),
    ).fetchall()


_RETRIEVAL_GROUP_COLUMNS = {
    "corpus-revision": "corpus_revision",
    "embedding-model": "embedding_model",
}


def retrieval_grouped_stats(
    conn: psycopg.Connection, days: int, by: str
) -> list[dict[str, Any]]:
    """Retrieval summary grouped by corpus revision or embedding model."""
    column = _RETRIEVAL_GROUP_COLUMNS[by]  # KeyError on unknown is deliberate
    return conn.execute(
        f"SELECT {column} AS grp, COUNT(*) AS n, "
        "AVG(CASE WHEN fallback_to_chunks THEN 1.0 ELSE 0.0 END) AS fallback_rate, "
        "AVG(coverage_score) AS avg_coverage "
        "FROM query_traces "
        "WHERE created_at >= now() - make_interval(days => %s) "
        "GROUP BY 1 ORDER BY n DESC",
        (days,),
    ).fetchall()


def ask_summary_stats(conn: psycopg.Connection, days: int) -> dict[str, Any]:
    """Ask volume, refusal rate, token totals, and summed cost estimate."""
    return conn.execute(
        "SELECT COUNT(*) AS n, "
        "AVG(CASE WHEN refused THEN 1.0 ELSE 0.0 END) AS refusal_rate, "
        "COALESCE(SUM(input_tokens), 0) AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0) AS output_tokens, "
        "COALESCE(SUM(cost_estimate), 0.0) AS cost_estimate "
        "FROM ask_traces "
        "WHERE created_at >= now() - make_interval(days => %s)",
        (days,),
    ).fetchone()


def ask_by_model_stats(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Ask volume and cost grouped by model."""
    return conn.execute(
        "SELECT model, COUNT(*) AS n, "
        "AVG(CASE WHEN refused THEN 1.0 ELSE 0.0 END) AS refusal_rate, "
        "COALESCE(SUM(input_tokens), 0) AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0) AS output_tokens, "
        "COALESCE(SUM(cost_estimate), 0.0) AS cost_estimate "
        "FROM ask_traces "
        "WHERE created_at >= now() - make_interval(days => %s) "
        "GROUP BY model ORDER BY n DESC",
        (days,),
    ).fetchall()


def curate_run_stats(conn: psycopg.Connection, days: int) -> dict[str, Any]:
    """Completed curate-run count, avg duration, and avg signal yield."""
    return conn.execute(
        "SELECT COUNT(*) AS n, "
        "AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) AS avg_duration_s, "
        "AVG(signal_count) AS avg_signals "
        "FROM graph_analysis_runs "
        "WHERE completed_at IS NOT NULL "
        "AND started_at >= now() - make_interval(days => %s)",
        (days,),
    ).fetchone()


def sync_backlog_stats(conn: psycopg.Connection) -> dict[str, Any]:
    """Current sync backlog by (index_kind, state) plus the oldest pending age."""
    lag = conn.execute(
        "SELECT index_kind, state, n FROM v_sync_lag ORDER BY index_kind, state"
    ).fetchall()
    oldest = conn.execute(
        "SELECT EXTRACT(EPOCH FROM (now() - MIN(updated_at))) AS age_s "
        "FROM index_sync_state WHERE state = 'pending'"
    ).fetchone()
    return {"lag": lag, "oldest_pending_age_s": oldest["age_s"]}


def ingest_outcome_stats(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Source counts by inspection status over the window."""
    return conn.execute(
        "SELECT COALESCE(inspection_status::text, 'unknown') AS status, COUNT(*) AS n "
        "FROM sources "
        "WHERE ingested_at >= now() - make_interval(days => %s) "
        "GROUP BY 1 ORDER BY n DESC",
        (days,),
    ).fetchall()


def ingest_stage_stats(conn: psycopg.Connection, days: int) -> list[dict[str, Any]]:
    """Per-stage avg and p95 ingest latency from sources.metadata['stage_ms']."""
    return conn.execute(
        "SELECT key AS stage, COUNT(*) AS n, "
        "AVG(value::float8) AS avg_ms, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY value::float8) AS p95_ms "
        "FROM sources, LATERAL jsonb_each_text(metadata -> 'stage_ms') "
        "WHERE ingested_at >= now() - make_interval(days => %s) "
        "GROUP BY key ORDER BY key",
        (days,),
    ).fetchall()


# --- contradiction candidates (ADR-014, v0.3 Phase 1) -----------------------


def latest_signal_created_at(conn: psycopg.Connection, kind: str) -> Any | None:
    """The newest signal timestamp for ``kind`` — the proposal watermark."""
    row = conn.execute(
        "SELECT MAX(created_at) AS ts FROM graph_curation_signals "
        "WHERE kind = %s::curation_signal_kind",
        (kind,),
    ).fetchone()
    return row["ts"] if row else None


def signal_pair_slugs(conn: psycopg.Connection, kind: str) -> set[tuple[str, str]]:
    """Canonicalised (slug, slug) pairs already carrying a ``kind`` signal.

    Any status counts: a dropped candidate is a curator decision and is not
    re-proposed.
    """
    rows = conn.execute(
        "SELECT payload->>'from_slug' AS a, payload->>'to_slug' AS b "
        "FROM graph_curation_signals WHERE kind = %s::curation_signal_kind",
        (kind,),
    ).fetchall()
    return {tuple(sorted((r["a"], r["b"]))) for r in rows if r["a"] and r["b"]}


def concept_pages_changed_since(
    conn: psycopg.Connection, since: Any | None
) -> list[dict[str, Any]]:
    """Concept pages updated after ``since`` (all concept pages when None)."""
    if since is None:
        return conn.execute(
            "SELECT * FROM wiki_pages WHERE kind = 'concept' ORDER BY updated_at"
        ).fetchall()
    return conn.execute(
        "SELECT * FROM wiki_pages WHERE kind = 'concept' AND updated_at > %s "
        "ORDER BY updated_at",
        (since,),
    ).fetchall()
