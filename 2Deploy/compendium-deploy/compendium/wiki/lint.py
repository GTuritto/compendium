"""Frontmatter lint for wiki pages.

Per-page rules check a page in isolation (the vault writer runs these and
blocks a write on any ``error``). Cross-reference rules check a page against
the rest of the vault and PostgreSQL; ``compendium lint`` runs everything.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from compendium.wiki.page import (
    GENERATORS,
    PAGE_KINDS,
    PAGE_STATUSES,
    REQUIRED_ALL,
    Page,
    content_hash,
    parse_markdown,
)
from compendium.wiki.page_kind import ERROR, PAGE_KIND_REGISTRY, WARNING, LintContext

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class LintIssue:
    """A single lint finding."""

    rule: str
    severity: str
    message: str
    page: str = ""


def _is_iso(value: object) -> bool:
    try:
        datetime.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def lint_page(page: Page) -> list[LintIssue]:
    """Run the per-page rules against one page."""
    ref = page.slug or page.title or "(unknown)"
    issues: list[LintIssue] = []

    def add(rule: str, severity: str, message: str) -> None:
        issues.append(LintIssue(rule, severity, message, ref))

    for fieldname in REQUIRED_ALL:
        if not getattr(page, fieldname, ""):
            add("frontmatter-required-fields", ERROR,
                f"missing required field '{fieldname}'")

    if page.kind not in PAGE_KINDS:
        add("frontmatter-types", ERROR, f"invalid kind '{page.kind}'")
    if page.status not in PAGE_STATUSES:
        add("frontmatter-types", ERROR, f"invalid status '{page.status}'")
    if page.generator not in GENERATORS:
        add("frontmatter-types", ERROR, f"invalid generator '{page.generator}'")
    for fieldname in ("created_at", "updated_at"):
        value = getattr(page, fieldname)
        if value and not _is_iso(value):
            add("frontmatter-types", ERROR,
                f"'{fieldname}' is not an ISO-8601 timestamp")

    if page.slug and (not _SLUG_RE.match(page.slug) or len(page.slug) > 80):
        add("slug-matches-rules", ERROR,
            f"slug '{page.slug}' violates the slug rules")

    if page.id and not _is_uuid(page.id):
        add("id-is-uuid", ERROR, f"id '{page.id}' is not a valid UUID")

    if page.content_hash and page.content_hash != content_hash(page.body):
        add("content-hash-matches", ERROR,
            "content_hash does not match the recomputed body hash")

    kind = PAGE_KIND_REGISTRY.get(page.kind)
    if kind is not None:
        kind.lint_page(page, add)

    if page.aliases:
        lowered = [a.lower() for a in page.aliases]
        if len(lowered) != len(set(lowered)):
            add("aliases-no-duplicates", WARNING, "aliases contains duplicates")
        if page.title.lower() in lowered:
            add("aliases-no-duplicates", WARNING, "aliases includes the title")

    if not page.body.strip():
        add("body-non-empty", ERROR, "body is empty")

    return issues


def lint_vault(
    pages: list[Page], *, known_source_ids: set[str] | None = None
) -> list[LintIssue]:
    """Run per-page and cross-reference rules over a whole vault."""
    issues: list[LintIssue] = []
    for page in pages:
        issues.extend(lint_page(page))

    # Cross-page rules: build the shared context once, then each page's kind
    # runs its own resolution rule (concept topic-ids + alias accumulation,
    # topic parent + cycle, source source-id) through the registry.
    ctx = LintContext(
        topic_ids={p.id for p in pages if p.kind == "topic" and p.id},
        by_id={p.id: p for p in pages if p.id},
        known_source_ids=known_source_ids,
        alias_owners=defaultdict(set),
    )

    for page in pages:
        ref = page.slug or page.title

        def add(rule: str, severity: str, message: str, _ref: str = ref) -> None:
            issues.append(LintIssue(rule, severity, message, _ref))

        kind = PAGE_KIND_REGISTRY.get(page.kind)
        if kind is not None:
            kind.lint_vault(page, ctx, add)

    for alias, owners in ctx.alias_owners.items():
        if len(owners) > 1:
            issues.append(LintIssue(
                "alias-uniqueness", WARNING,
                f"alias '{alias}' is used by multiple concepts: {sorted(owners)}"))

    return issues


def load_vault_pages(vault_path: str) -> tuple[list[Page], list[LintIssue]]:
    """Load every page under ``vault/{concepts,topics,sources}/``.

    Returns the parsed pages and a list of issues for files that failed to
    parse.
    """
    root = Path(vault_path)
    pages: list[Page] = []
    issues: list[LintIssue] = []
    for subdir in ("concepts", "topics", "sources"):
        directory = root / subdir
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            try:
                pages.append(parse_markdown(path.read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                issues.append(LintIssue(
                    "page-parses", ERROR, f"could not parse: {exc}", str(path)))
    return pages, issues


def errors_only(issues: Iterable[LintIssue]) -> list[LintIssue]:
    """The error-severity subset of a list of issues."""
    return [issue for issue in issues if issue.severity == ERROR]
