"""Raw-SQL data access for the operational tables.

No ORM: queries are plain SQL over psycopg 3, which adapts JSONB, arrays,
UUID, and timestamps directly. Enum-typed columns are cast explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable
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


# --- wiki pages ------------------------------------------------------------


def insert_wiki_page(
    conn: psycopg.Connection,
    *,
    kind: str,
    slug: str,
    title: str,
    file_path: str,
    content_hash: str,
    status: str = "draft",
    aliases: list[str] | None = None,
) -> UUID:
    """Insert a row into ``wiki_pages`` and return its id."""
    row = conn.execute(
        """
        INSERT INTO wiki_pages (
            kind, slug, title, file_path, content_hash, status, aliases
        )
        VALUES (
            %(kind)s::page_kind, %(slug)s, %(title)s, %(file_path)s,
            %(content_hash)s, %(status)s::page_status, %(aliases)s::text[]
        )
        RETURNING id
        """,
        {
            "kind": kind,
            "slug": slug,
            "title": title,
            "file_path": file_path,
            "content_hash": content_hash,
            "status": status,
            "aliases": aliases if aliases is not None else [],
        },
    ).fetchone()
    assert row is not None
    return row["id"]


def get_wiki_page(conn: psycopg.Connection, page_id: UUID) -> dict[str, Any] | None:
    """Read a ``wiki_pages`` row by id, or None if absent."""
    return conn.execute(
        "SELECT * FROM wiki_pages WHERE id = %s", (page_id,)
    ).fetchone()
