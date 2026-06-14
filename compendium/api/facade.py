"""The shared access-surface facade (ADR-011, v0.2 Phase 7).

One home for the six access-surface verbs — ``query``, ``ask``, ``ingest``,
``page_get``, ``page_list``, ``index_status`` — over the existing
``pipeline.query``, ``answer.ask``, the ingestion pipeline, the index status
report, and the repository readers. The MCP and HTTP transports are thin shells
over this module; neither holds business logic, so the two surfaces cannot
drift. Functions return the existing dataclass shapes (plus a small dict shape
for ``page_get`` / ``page_list``); transports serialize via
``compendium.api.serialize.to_payload``.

Curator/operations verbs (``curate``, ``trace``, ``page promote``, ``reindex``,
``graph link/rebuild``, ``synth``) are deliberately absent: agents read memory
and write documents; everything else stays CLI-only (ADR-011).
"""

from __future__ import annotations

import base64
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from compendium.config import load_config

# The six verbs the access surface exposes, in ADR-011 order.
VERBS = ("query", "ask", "ingest", "page_get", "page_list", "index_status")


def query(text: str) -> Any:
    """Page-first retrieval: a ``RetrievalResult`` (ranked pages + coverage + trace)."""
    from compendium.retrieve.pipeline import query as _query

    return _query(text)


def ask(question: str, *, on_token: Callable[[str], None] | None = None) -> Any:
    """A composed answer over the top-K pages: an ``AskResult`` (Phase 6).

    Streams composition deltas to ``on_token`` when supplied; writes the
    ``ask_traces`` row joined to ``query_traces`` either way.
    """
    from compendium.answer import ask as _ask

    return _ask(question, on_token=on_token)


def ingest(
    *,
    path: str | None = None,
    content: bytes | None = None,
    content_base64: str | None = None,
    filename: str | None = None,
    kind: str,
    mine: bool = False,
) -> Any:
    """Ingest one source from a path, raw bytes, or base64 bytes; auto-run sync.

    A deliberate departure from the CLI's two-step (ADR-011): agents expect
    "I added it; query finds it", so this runs ``index sync`` for the affected
    stores before returning. The facade owns the surface's input coercion
    (arch-facade-ingest-coercion): ``content_base64`` is decoded here, and a
    missing or invalid input raises ``ValueError`` with one message the
    transports render natively (HTTP 400; MCP propagates). Raw ``content`` is
    written to a temp file derived from ``filename`` (the ingestion core stays
    path-based) and removed after. Returns the single ``IngestResult`` (or the
    list when a path expands to several sources).
    """
    from compendium.index.sync import sync_pending
    from compendium.ingest.pipeline import ingest as _ingest

    if content_base64 is not None:
        try:
            content = base64.b64decode(content_base64)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid content_base64: {exc}") from exc

    if content is not None:
        tmpdir = tempfile.mkdtemp(prefix="compendium-ingest-")
        name = Path(filename).name if filename else "upload"
        tmp_path = Path(tmpdir) / name
        tmp_path.write_bytes(content)
        try:
            results = _ingest(str(tmp_path), kind=kind, mine=mine)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
    elif path is not None:
        results = _ingest(path, kind=kind, mine=mine)
    else:
        raise ValueError("ingest requires 'path' or 'content_base64'")

    # Auto-sync so the new source is immediately retrievable by the next query.
    sync_pending()

    if len(results) == 1:
        return results[0]
    return results


def page_get(kind: str, slug: str) -> dict[str, Any] | None:
    """Frontmatter + body Markdown for one page, or ``None`` when absent.

    ``None`` is the access surface's one not-found decision
    (arch-facade-ingest-coercion); each transport renders it natively — HTTP
    as 404, MCP as JSON ``null`` — without deciding independently.
    """
    from compendium.db import repository
    from compendium.db.connection import connection

    vault_path = load_config().vault_path
    with connection() as conn:
        row = repository.get_wiki_page_by_slug(conn, kind, slug)
    if not row:
        return None

    markdown = ""
    file_path = row.get("file_path")
    if file_path:
        try:
            markdown = (Path(vault_path) / file_path).read_text(encoding="utf-8")
        except OSError:
            markdown = ""
    return {
        "kind": row["kind"],
        "slug": row["slug"],
        "title": row["title"],
        "status": row["status"],
        "aliases": row.get("aliases") or [],
        "file_path": file_path,
        "markdown": markdown,
    }


def page_list(
    *, kind: str | None = None, status: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """A filtered, newest-first page list for discovery."""
    from compendium.db import repository
    from compendium.db.connection import connection

    with connection() as conn:
        return repository.list_wiki_pages(conn, kind=kind, status=status, limit=limit)


def index_status() -> Any:
    """Derived-index counts and sync-lag rows: an ``IndexStatusReport``."""
    from compendium.index.sync import status

    return status()


# --- agent object store (ADR-017): verbatim agent storage + promote ---------
# Agent-write verbs ("agents read memory and write documents"). The object
# store is invisible to retrieval until an object is promoted.

OBJECT_VERBS = (
    "object_put", "object_get", "object_list", "object_delete", "object_promote",
)


def _object_meta(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-native object metadata (no body)."""
    return {
        "id": str(row["id"]),
        "collection": row["collection"],
        "key": row["key"],
        "content_type": row["content_type"],
        "metadata": row.get("metadata") or {},
        "size": row.get("size"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def object_put(
    key: str,
    *,
    collection: str = "default",
    content_text: str | None = None,
    content_base64: str | None = None,
    content_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from compendium import objects

    if content_base64 is not None:
        try:
            body = base64.b64decode(content_base64)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid content_base64: {exc}") from exc
        ctype = content_type or "application/octet-stream"
    elif content_text is not None:
        body = content_text.encode("utf-8")
        ctype = content_type or "text/plain"
    else:
        raise ValueError("object_put requires 'content_text' or 'content_base64'")
    row = objects.put(
        key, body, collection=collection, content_type=ctype, metadata=metadata
    )
    return _object_meta(row)


def object_get(key: str, *, collection: str = "default") -> dict[str, Any] | None:
    from compendium import objects

    row = objects.get(key, collection=collection)
    if row is None:
        return None
    out = _object_meta(row)
    out["size"] = len(row["body"])
    out["body_base64"] = base64.b64encode(row["body"]).decode("ascii")  # verbatim
    out["body_text"] = (
        row["body"].decode("utf-8")
        if (row["content_type"] or "").startswith("text")
        else None
    )
    return out


def object_list(
    *, collection: str | None = None, prefix: str | None = None
) -> list[dict[str, Any]]:
    from compendium import objects

    return [_object_meta(r) for r in objects.list_objects(collection=collection, prefix=prefix)]


def object_delete(key: str, *, collection: str = "default") -> dict[str, Any]:
    from compendium import objects

    return {
        "collection": collection,
        "key": key,
        "deleted": objects.delete(key, collection=collection),
    }


def object_promote(
    key: str, *, collection: str = "default", kind: str = "note"
) -> dict[str, Any]:
    from compendium import objects

    return objects.promote(key, collection=collection, kind=kind)
