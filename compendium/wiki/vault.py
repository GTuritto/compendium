"""The vault writer: persist a page to disk and to PostgreSQL.

A write lints the page first and refuses it on any error-severity rule. It
records a ``wiki_pages`` row (insert or update) and a ``wiki_page_revisions``
snapshot, and writes the canonical Markdown file under ``vault/``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from compendium.db import repository
from compendium.wiki.lint import LintIssue, errors_only, lint_page
from compendium.wiki.page import Page, content_hash

_SUBDIR = {"concept": "concepts", "topic": "topics", "source": "sources"}


class LintError(Exception):
    """Raised when a page fails error-severity lint and cannot be written."""

    def __init__(self, issues: list[LintIssue]) -> None:
        self.issues = issues
        super().__init__(
            "; ".join(f"{i.rule}: {i.message}" for i in issues)
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_page(conn: psycopg.Connection, page: Page, *, vault_path: str) -> Page:
    """Lint, then write ``page`` to the vault and to PostgreSQL.

    If ``page.id`` is set the page is updated in place; otherwise a new page
    is created and ``page.id`` is filled in. Raises :class:`LintError` if any
    error-severity lint rule fails.
    """
    now = _now_iso()
    page.corpus_revision = page.corpus_revision or repository.ensure_corpus_revision(
        conn
    )

    is_update = bool(page.id)
    if is_update:
        existing = repository.get_wiki_page(conn, UUID(page.id))
        if existing is not None:
            page.created_at = existing["created_at"].isoformat()
        elif not page.created_at:
            page.created_at = now
    else:
        page.id = str(uuid4())
        page.created_at = page.created_at or now
    page.updated_at = now
    page.content_hash = content_hash(page.body)

    errors = errors_only(lint_page(page))
    if errors:
        raise LintError(errors)

    rel_path = f"{_SUBDIR[page.kind]}/{page.slug}.md"
    page_uuid = UUID(page.id)
    fields = {
        "slug": page.slug,
        "title": page.title,
        "file_path": rel_path,
        "content_hash": page.content_hash,
        "status": page.status,
        "corpus_revision": page.corpus_revision,
        "aliases": page.aliases if page.kind == "concept" else [],
        "parent_topic_id": (
            UUID(page.parent_topic_id)
            if page.kind == "topic" and page.parent_topic_id
            else None
        ),
        "source_id": (
            UUID(page.source_id) if page.kind == "source" and page.source_id else None
        ),
        "source_kind": page.source_kind if page.kind == "source" else None,
        "source_metadata": page.source_metadata if page.kind == "source" else None,
        "inspection_status": (
            page.inspection_status if page.kind == "source" else None
        ),
    }
    if is_update:
        repository.update_wiki_page(conn, page_uuid, **fields)
    else:
        repository.insert_wiki_page(conn, page_id=page_uuid, kind=page.kind, **fields)

    path = Path(vault_path) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.to_markdown(), encoding="utf-8")

    revision_id = repository.insert_wiki_page_revision(
        conn,
        page_id=page_uuid,
        body=page.body,
        content_hash=page.content_hash,
        frontmatter=page.frontmatter(),
        generator=page.generator,
    )
    repository.set_current_revision(conn, page_uuid, revision_id)
    if page.kind == "concept":
        repository.set_page_topics(
            conn, page_uuid, [UUID(t) for t in page.topic_ids]
        )
    return page
