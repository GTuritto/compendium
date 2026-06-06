"""The single home for per-page-kind rules.

Each wiki page kind (`source`, `concept`, `topic`) has distinct required
frontmatter fields, a distinct frontmatter shape, distinct vault DB fields, a
distinct vault subdirectory, and distinct lint rules. Those rules used to be
spread across `page.py`, `lint.py`, and `vault.py` as parallel `if/elif kind`
ladders; they now live here, one :class:`PageKind` record per kind, consulted by
those three modules.

`Page` stays a flat data carrier (this module imports it for typing only); this
is a strategy registry over the *rules*, not a subclassing of the *data*.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from compendium.wiki.page import Page

# Lint severities (kept equal to lint.ERROR / lint.WARNING; lint imports these
# back from here so there is one definition and no import cycle).
ERROR = "error"
WARNING = "warning"

AddFn = Callable[[str, str, str], None]


@dataclass
class LintContext:
    """Cross-page context a kind's vault-lint hook reads (built once per run)."""

    topic_ids: set[str]
    by_id: dict[str, "Page"]
    known_source_ids: set[str] | None
    alias_owners: dict[str, set[str]]


@dataclass(frozen=True)
class PageKind:
    """One page kind and the rules that govern it."""

    name: str
    subdir: str
    required_fields: tuple[str, ...]
    frontmatter_fields: Callable[["Page"], dict[str, Any]]
    db_fields: Callable[["Page"], dict[str, Any]]
    writes_topic_links: bool
    lint_page: Callable[["Page", AddFn], None]
    lint_vault: Callable[["Page", LintContext, AddFn], None]


# --- concept ---------------------------------------------------------------


def _concept_frontmatter(p: "Page") -> dict[str, Any]:
    return {"topic_ids": list(p.topic_ids), "aliases": list(p.aliases)}


def _concept_db_fields(p: "Page") -> dict[str, Any]:
    return {
        "aliases": list(p.aliases),
        "parent_topic_id": None,
        "source_id": None,
        "source_kind": None,
        "source_metadata": None,
        "inspection_status": None,
    }


def _concept_lint_page(p: "Page", add: AddFn) -> None:
    # No concept-only per-page rule (the alias dup/title check is universal).
    return None


def _concept_lint_vault(p: "Page", ctx: LintContext, add: AddFn) -> None:
    for topic_id in p.topic_ids:
        if topic_id not in ctx.topic_ids:
            add("topic-ids-resolve", ERROR,
                f"topic_id '{topic_id}' does not resolve to a topic page")
    ref = p.slug or p.title
    for alias in p.aliases:
        ctx.alias_owners[alias.lower()].add(ref)


# --- topic -----------------------------------------------------------------


def _topic_frontmatter(p: "Page") -> dict[str, Any]:
    return {"parent_topic_id": p.parent_topic_id}


def _topic_db_fields(p: "Page") -> dict[str, Any]:
    return {
        "aliases": [],
        "parent_topic_id": p.parent_topic_id,
        "source_id": None,
        "source_kind": None,
        "source_metadata": None,
        "inspection_status": None,
    }


def _topic_lint_page(p: "Page", add: AddFn) -> None:
    return None


def _topic_lint_vault(p: "Page", ctx: LintContext, add: AddFn) -> None:
    if p.parent_topic_id and p.parent_topic_id not in ctx.topic_ids:
        add("parent-topic-resolves", ERROR,
            f"parent_topic_id '{p.parent_topic_id}' does not resolve")
    # Cycle in the parent chain (walk via the by_id map).
    seen: set[str] = set()
    current: "Page | None" = p
    while current is not None and current.parent_topic_id:
        if current.id in seen:
            add("no-cycle-in-topic-tree", ERROR, "cycle in the topic parent chain")
            return
        seen.add(current.id)
        current = ctx.by_id.get(current.parent_topic_id)


# --- source ----------------------------------------------------------------


def _source_frontmatter(p: "Page") -> dict[str, Any]:
    return {
        "source_id": p.source_id,
        "source_kind": p.source_kind,
        "source_metadata": p.source_metadata or {},
        "inspection_status": p.inspection_status,
    }


def _source_db_fields(p: "Page") -> dict[str, Any]:
    return {
        "aliases": [],
        "parent_topic_id": None,
        "source_id": p.source_id,
        "source_kind": p.source_kind,
        "source_metadata": p.source_metadata,
        "inspection_status": p.inspection_status,
    }


def _source_lint_page(p: "Page", add: AddFn) -> None:
    for fieldname in ("source_id", "source_kind", "inspection_status"):
        if not getattr(p, fieldname):
            add("kind-specific-fields", ERROR, f"source page missing '{fieldname}'")


def _source_lint_vault(p: "Page", ctx: LintContext, add: AddFn) -> None:
    if ctx.known_source_ids is not None and p.source_id and p.source_id not in ctx.known_source_ids:
        add("source-id-resolves", ERROR,
            f"source_id '{p.source_id}' has no row in sources")


# --- registry --------------------------------------------------------------

PAGE_KIND_REGISTRY: dict[str, PageKind] = {
    "concept": PageKind(
        name="concept", subdir="concepts", required_fields=("topic_ids",),
        frontmatter_fields=_concept_frontmatter, db_fields=_concept_db_fields,
        writes_topic_links=True,
        lint_page=_concept_lint_page, lint_vault=_concept_lint_vault,
    ),
    "topic": PageKind(
        name="topic", subdir="topics", required_fields=("parent_topic_id",),
        frontmatter_fields=_topic_frontmatter, db_fields=_topic_db_fields,
        writes_topic_links=False,
        lint_page=_topic_lint_page, lint_vault=_topic_lint_vault,
    ),
    "source": PageKind(
        name="source", subdir="sources",
        required_fields=("source_id", "source_kind", "source_metadata", "inspection_status"),
        frontmatter_fields=_source_frontmatter, db_fields=_source_db_fields,
        writes_topic_links=False,
        lint_page=_source_lint_page, lint_vault=_source_lint_vault,
    ),
}

# Derived (single source for page.py's public names).
PAGE_KIND_NAMES: tuple[str, ...] = tuple(PAGE_KIND_REGISTRY)
REQUIRED_BY_KIND: dict[str, tuple[str, ...]] = {
    name: k.required_fields for name, k in PAGE_KIND_REGISTRY.items()
}
