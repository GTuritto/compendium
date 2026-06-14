"""Agent object store + one-way promote into synthesis (ADR-017, v0.5).

A verbatim PostgreSQL-backed key-value store for a colocated agent: put/get/
list/delete bytes byte-for-byte. It is NOT the wiki and NOT a derived index —
nothing here is searchable until ``promote`` runs an object through the normal
ingest pipeline to become a ``source`` page (indexed, queryable). Promote is
one-way and stops at the source layer: it never creates concept/topic pages or
edges, so synthesis stays curator-driven. Single namespace, no auth (the
loopback/LAN posture of ADR-011).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from compendium.db import repository
from compendium.db.connection import connection

DEFAULT_COLLECTION = "default"


def put(
    key: str,
    body: bytes,
    *,
    collection: str = DEFAULT_COLLECTION,
    content_type: str = "text/plain",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connection() as conn:
        row = repository.put_object(
            conn, collection=collection, key=key, body=body,
            content_type=content_type, metadata=metadata,
        )
        conn.commit()
        return row


def get(key: str, *, collection: str = DEFAULT_COLLECTION) -> dict[str, Any] | None:
    with connection() as conn:
        return repository.get_object(conn, collection=collection, key=key)


def list_objects(
    *, collection: str | None = None, prefix: str | None = None
) -> list[dict[str, Any]]:
    with connection() as conn:
        return repository.list_objects(conn, collection=collection, prefix=prefix)


def delete(key: str, *, collection: str = DEFAULT_COLLECTION) -> bool:
    with connection() as conn:
        ok = repository.delete_object(conn, collection=collection, key=key)
        conn.commit()
        return ok


def promote(
    key: str, *, collection: str = DEFAULT_COLLECTION, kind: str = "note"
) -> dict[str, Any]:
    """Run an object's body through ingest to become a queryable ``source`` page,
    provenance-linked back to the object. One-way; never synthesizes."""
    obj = get(key, collection=collection)
    if obj is None:
        raise KeyError(f"no object {collection}/{key}")

    from compendium.api import facade
    from compendium.config import load_config
    from compendium.index.sync import sync_pending
    from compendium.wiki.source_page import generate_source_page

    name = key if Path(key).suffix else key + (
        ".md" if (obj["content_type"] or "").startswith("text") else ".bin"
    )
    result = facade.ingest(content=obj["body"], filename=name, kind=kind)
    source_id = getattr(result, "source_id", None)
    slug = None
    if source_id is not None:
        with connection() as conn:
            page = generate_source_page(
                conn, source_id, vault_path=load_config().vault_path
            )
            conn.commit()
            slug = page.slug if page else None
        sync_pending()  # index the new source page
        # provenance: record the resulting source on the object (LWW re-put).
        meta = dict(obj.get("metadata") or {})
        meta["promoted_to_source"] = str(source_id)
        put(
            key, obj["body"], collection=collection,
            content_type=obj["content_type"], metadata=meta,
        )
    return {
        "source_id": str(source_id) if source_id else None,
        "slug": slug,
        "status": getattr(result, "status", None),
    }
