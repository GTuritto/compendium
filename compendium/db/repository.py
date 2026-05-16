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
