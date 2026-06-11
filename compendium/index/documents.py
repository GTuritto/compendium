"""Project PostgreSQL rows (plus the vault body) into index documents.

Pure functions: dict in, dict out, no I/O. The structured fields of a page
come from its ``wiki_pages`` row; its body text comes from the canonical vault
file. A chunk comes entirely from PostgreSQL (its ``chunks`` row joined to the
source title and kind). OpenSearch wants ISO timestamps; Qdrant wants unix-ms
integers and a short body preview.

**The shape is declared once** (arch-index-document-shape): each field appears
on exactly one row of ``_page_rows`` / ``_chunk_rows`` carrying its OpenSearch
document value and its Qdrant payload value (``_SAME`` when the stores agree,
``_OMIT`` where a store does not carry the field). The four builders, the
field-name constants, and the searchable subsets all derive from those rows —
the OpenSearch mappings and the retrieval-side readers are test-asserted
against the constants, so a renamed field fails fast instead of silently
returning empty strings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

_PREVIEW_CHARS = 200

# Row markers: the payload value equals the document value / the store omits it.
_SAME = object()
_OMIT = object()

# One row per field: (name, document_value, payload_value).
_Rows = list[tuple[str, Any, Any]]


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


# --- the shape (one row per field; both store values side by side) ----------


def _page_rows(page: dict[str, Any], *, body: str, topic_ids: list[str]) -> _Rows:
    return [
        ("id", str(page["id"]), _SAME),
        ("kind", page["kind"], _SAME),
        ("title", page["title"], _SAME),
        ("slug", page["slug"], _SAME),
        ("status", page["status"], _SAME),
        ("corpus_revision", page.get("corpus_revision"), _SAME),
        ("topic_ids", [str(t) for t in topic_ids], _SAME),
        (
            "parent_topic_id",
            str(page["parent_topic_id"]) if page.get("parent_topic_id") else None,
            _SAME,
        ),
        ("source_id", str(page["source_id"]) if page.get("source_id") else None, _SAME),
        ("source_kind", page.get("source_kind"), _SAME),
        ("inspection_status", page.get("inspection_status"), _OMIT),
        ("aliases", list(page.get("aliases") or []), _OMIT),
        ("body", body, _OMIT),
        ("created_at", _iso(page.get("created_at")), _unix_ms(page.get("created_at"))),
        ("updated_at", _iso(page.get("updated_at")), _unix_ms(page.get("updated_at"))),
    ]


def _chunk_rows(chunk: dict[str, Any]) -> _Rows:
    return [
        ("id", str(chunk["id"]), _SAME),
        ("source_id", str(chunk["source_id"]), _SAME),
        ("source_kind", chunk.get("source_kind"), _SAME),
        ("source_title", chunk.get("source_title"), _OMIT),
        ("position", chunk["position"], _SAME),
        ("parent_section", chunk.get("parent_section"), _SAME),
        ("body", chunk["body"], _OMIT),
        ("body_preview", _OMIT, " ".join(chunk["body"].split())[:_PREVIEW_CHARS]),
        ("token_count", chunk.get("token_count"), _SAME),
        ("created_at", _iso(chunk.get("created_at")), _unix_ms(chunk.get("created_at"))),
    ]


def _document(rows: _Rows) -> dict[str, Any]:
    return {name: doc for name, doc, _ in rows if doc is not _OMIT}


def _payload(rows: _Rows) -> dict[str, Any]:
    return {
        name: (doc if pay is _SAME else pay)
        for name, doc, pay in rows
        if pay is not _OMIT
    }


# --- the derived contract (names; consumed by mappings + search + tests) ----

_PAGE_PROBE = _page_rows(
    {"id": "x", "kind": "", "title": "", "slug": "", "status": ""}, body="", topic_ids=[]
)
_CHUNK_PROBE = _chunk_rows({"id": "x", "source_id": "x", "position": 0, "body": ""})

PAGE_DOCUMENT_FIELDS: tuple[str, ...] = tuple(n for n, d, _ in _PAGE_PROBE if d is not _OMIT)
PAGE_PAYLOAD_FIELDS: tuple[str, ...] = tuple(n for n, _, p in _PAGE_PROBE if p is not _OMIT)
CHUNK_DOCUMENT_FIELDS: tuple[str, ...] = tuple(n for n, d, _ in _CHUNK_PROBE if d is not _OMIT)
CHUNK_PAYLOAD_FIELDS: tuple[str, ...] = tuple(n for n, _, p in _CHUNK_PROBE if p is not _OMIT)

# The lexical-search subsets (boosts stay local to retrieve/search.py).
PAGE_SEARCHABLE_FIELDS: tuple[str, ...] = ("title", "aliases", "body")
CHUNK_SEARCHABLE_FIELDS: tuple[str, ...] = ("source_title", "body")


# --- the builders (derived from the rows) ------------------------------------


def page_document(page: dict[str, Any], *, body: str, topic_ids: list[str]) -> dict[str, Any]:
    """The OpenSearch ``pages`` document for a wiki page."""
    return _document(_page_rows(page, body=body, topic_ids=topic_ids))


def page_payload(page: dict[str, Any], *, topic_ids: list[str]) -> dict[str, Any]:
    """The Qdrant ``pages`` payload for a wiki page."""
    return _payload(_page_rows(page, body="", topic_ids=topic_ids))


def chunk_document(chunk: dict[str, Any]) -> dict[str, Any]:
    """The OpenSearch ``chunks`` document for a chunk row (joined to its source)."""
    return _document(_chunk_rows(chunk))


def chunk_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    """The Qdrant ``chunks`` payload for a chunk row."""
    return _payload(_chunk_rows(chunk))
