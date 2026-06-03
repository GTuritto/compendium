"""Project PostgreSQL rows (plus the vault body) into index documents.

Pure functions: dict in, dict out, no I/O. The structured fields of a page
come from its ``wiki_pages`` row; its body text comes from the canonical vault
file. A chunk comes entirely from PostgreSQL (its ``chunks`` row joined to the
source title and kind). OpenSearch wants ISO timestamps; Qdrant wants unix-ms
integers and a short body preview.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

_PREVIEW_CHARS = 200


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _unix_ms(value: Any) -> int | None:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    return None


def page_embed_text(title: str, body: str) -> str:
    """The text embedded for a page: its title and body."""
    return f"{title}\n\n{body}".strip()


def chunk_embed_text(body: str) -> str:
    """The text embedded for a chunk: its body."""
    return body


def page_document(page: dict[str, Any], *, body: str, topic_ids: list[str]) -> dict[str, Any]:
    """The OpenSearch ``pages`` document for a wiki page."""
    return {
        "id": str(page["id"]),
        "kind": page["kind"],
        "title": page["title"],
        "slug": page["slug"],
        "status": page["status"],
        "corpus_revision": page.get("corpus_revision"),
        "topic_ids": [str(t) for t in topic_ids],
        "parent_topic_id": (
            str(page["parent_topic_id"]) if page.get("parent_topic_id") else None
        ),
        "source_id": str(page["source_id"]) if page.get("source_id") else None,
        "source_kind": page.get("source_kind"),
        "inspection_status": page.get("inspection_status"),
        "aliases": list(page.get("aliases") or []),
        "body": body,
        "created_at": _iso(page.get("created_at")),
        "updated_at": _iso(page.get("updated_at")),
    }


def page_payload(page: dict[str, Any], *, topic_ids: list[str]) -> dict[str, Any]:
    """The Qdrant ``pages`` payload for a wiki page."""
    return {
        "id": str(page["id"]),
        "kind": page["kind"],
        "title": page["title"],
        "slug": page["slug"],
        "status": page["status"],
        "corpus_revision": page.get("corpus_revision"),
        "topic_ids": [str(t) for t in topic_ids],
        "parent_topic_id": (
            str(page["parent_topic_id"]) if page.get("parent_topic_id") else None
        ),
        "source_id": str(page["source_id"]) if page.get("source_id") else None,
        "source_kind": page.get("source_kind"),
        "created_at": _unix_ms(page.get("created_at")),
        "updated_at": _unix_ms(page.get("updated_at")),
    }


def chunk_document(chunk: dict[str, Any]) -> dict[str, Any]:
    """The OpenSearch ``chunks`` document for a chunk row (joined to its source)."""
    return {
        "id": str(chunk["id"]),
        "source_id": str(chunk["source_id"]),
        "source_kind": chunk.get("source_kind"),
        "source_title": chunk.get("source_title"),
        "position": chunk["position"],
        "parent_section": chunk.get("parent_section"),
        "body": chunk["body"],
        "token_count": chunk.get("token_count"),
        "created_at": _iso(chunk.get("created_at")),
    }


def chunk_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    """The Qdrant ``chunks`` payload for a chunk row."""
    return {
        "id": str(chunk["id"]),
        "source_id": str(chunk["source_id"]),
        "source_kind": chunk.get("source_kind"),
        "position": chunk["position"],
        "parent_section": chunk.get("parent_section"),
        "body_preview": " ".join(chunk["body"].split())[:_PREVIEW_CHARS],
        "token_count": chunk.get("token_count"),
        "created_at": _unix_ms(chunk.get("created_at")),
    }
