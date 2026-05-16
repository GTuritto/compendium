"""Raw-SQL data access for the operational tables.

Phase 1 covers ``sources`` and ``wiki_pages`` (insert and read-back). Later
phases extend this module. No ORM: queries are plain SQL over psycopg 3,
which adapts JSONB, arrays, UUID, and timestamps directly. Enum-typed columns
are cast explicitly in SQL.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Json


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


def get_source(conn: psycopg.Connection, source_id: UUID) -> dict[str, Any] | None:
    """Read a ``sources`` row by id, or None if absent."""
    return conn.execute(
        "SELECT * FROM sources WHERE id = %s", (source_id,)
    ).fetchone()


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
