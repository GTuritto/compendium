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
    filename: str | None = None,
    kind: str,
    mine: bool = False,
) -> Any:
    """Ingest one source from a file path or raw bytes, then auto-run index sync.

    A deliberate departure from the CLI's two-step (ADR-011): agents expect
    "I added it; query finds it", so this runs ``index sync`` for the affected
    stores before returning. Raw ``content`` is written to a temp file derived
    from ``filename`` (the ingestion core stays path-based) and removed after.
    Returns the single ``IngestResult`` (or the list when a path expands to
    several sources).
    """
    from compendium.index.sync import sync_pending
    from compendium.ingest.pipeline import ingest as _ingest

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
        raise ValueError("ingest requires either 'path' or 'content'")

    # Auto-sync so the new source is immediately retrievable by the next query.
    sync_pending()

    if len(results) == 1:
        return results[0]
    return results


def page_get(kind: str, slug: str) -> dict[str, Any] | None:
    """Frontmatter + body Markdown for one page, or None when it does not exist."""
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
