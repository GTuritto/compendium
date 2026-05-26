"""Promotion: a recorded wiki-page lifecycle transition (ADR-007).

``promote`` flips a page's status in one transaction: it re-writes the page
through the Phase 3 vault writer with the new status and ``human`` generator (so
the vault file stays canonical, a fresh revision is snapshotted, and the derived
indexes are re-enqueued), then records a ``promotion_events`` row linking the
old and new revisions. This is the v0.1 promotion primitive the Phase 9 curator
loop will reuse. ``merge``/``split`` kinds exist in the schema but are not
exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from compendium.db import repository
from compendium.db.connection import connection
from compendium.wiki.page import parse_markdown
from compendium.wiki.vault import write_page

# to_status -> (required current status, promotion_kind)
_TRANSITIONS = {
    "canonical": ("draft", "draft_to_canonical"),
    "deprecated": ("canonical", "canonical_to_deprecated"),
}


class PageNotFound(Exception):
    """Raised when no page matches the slug."""


class InvalidTransition(Exception):
    """Raised when the page's current status cannot move to the target."""


@dataclass
class PromotionResult:
    slug: str
    kind: str           # page kind (concept/topic/source)
    from_status: str
    to_status: str
    promotion_kind: str
    event_id: str


def promote(slug: str, to_status: str, *, vault_path: str, notes: str | None = None) -> PromotionResult:
    """Transition a page to ``to_status``, recording a promotion event."""
    if to_status not in _TRANSITIONS:
        raise ValueError(f"unsupported target status: {to_status}")
    required_from, promotion_kind = _TRANSITIONS[to_status]

    with connection() as conn:
        page = repository.resolve_page_by_slug(conn, slug)
        if page is None:
            raise PageNotFound(slug)
        from_status = page["status"]
        if from_status != required_from:
            raise InvalidTransition(
                f"cannot promote '{slug}' from '{from_status}' to '{to_status}' "
                f"(requires '{required_from}')"
            )
        page_id = page["id"]
        from_revision_id = page["current_revision_id"]

        # Re-write through the vault writer with the new status (keeps the vault
        # canonical, snapshots a human revision, re-enqueues the indexes).
        model = parse_markdown((Path(vault_path) / page["file_path"]).read_text("utf-8"))
        model.id = str(page_id)
        model.status = to_status
        model.generator = "human"
        write_page(conn, model, vault_path=vault_path)

        updated = repository.get_wiki_page(conn, page_id)
        to_revision_id = updated["current_revision_id"]
        event_id = repository.record_promotion(
            conn,
            page_id=page_id,
            kind=promotion_kind,
            from_revision_id=from_revision_id,
            to_revision_id=to_revision_id,
            notes=notes or f"promote to {to_status}",
        )

        # Curation loop (Phase 9): if this page addresses an open signal, close
        # it and add SYNTHESIZES edges. No-op for ordinary promotions.
        from compendium.curate.promote_hook import address_on_promote

        address_on_promote(conn, updated, str(to_revision_id), vault_path)

    return PromotionResult(
        slug=slug,
        kind=page["kind"],
        from_status=from_status,
        to_status=to_status,
        promotion_kind=promotion_kind,
        event_id=str(event_id),
    )
