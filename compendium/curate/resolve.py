"""``compendium curate resolve`` — the curator's verdict on a signal (v0.3 Phase 1).

The generic inverse of ``curate run``: ``--drop`` works for every signal kind
(the curator declining a suggestion is itself a recorded decision — a dropped
``contradiction_candidate`` is never re-proposed); ``--approve`` dispatches
through a per-kind action map. Its first entry is ``contradiction_candidate``
(ADR-014): approval writes the ``CONTRADICTS`` edge through the existing
curator path (``graph/links.link`` → the ADR-013 dual-write coordinator), so
the edge lands with ``extracted_by="curator"`` provenance, is persisted to
PostgreSQL, and survives ``graph rebuild`` — then the signal becomes
``addressed``. Kinds without an approve action answer with a clear error
naming their path (``curate synth`` for the coverage-shaped signals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from compendium.db import repository
from compendium.db.connection import connection


class ResolveError(Exception):
    """Raised when a signal cannot be resolved (unknown id, settled status,
    or an approve without a defined action for the kind)."""


@dataclass
class ResolveResult:
    """What the verdict did, for the CLI/TUI to render."""

    signal_id: str
    kind: str
    action: str  # "approved" | "dropped"
    detail: str


_RESOLVABLE_STATUSES = ("open", "in_progress")


def _approve_contradiction(conn: Any, signal: dict[str, Any]) -> str:
    """Write the curator-owned CONTRADICTS edge for an approved candidate."""
    from compendium.graph.links import LinkError, link

    payload = signal["payload"] or {}
    from_slug, to_slug = payload.get("from_slug"), payload.get("to_slug")
    if not from_slug or not to_slug:
        raise ResolveError(
            f"signal {signal['id']} payload carries no page slugs; cannot approve"
        )
    try:
        link(from_slug, to_slug, "CONTRADICTS")
    except LinkError as exc:
        raise ResolveError(str(exc)) from exc
    return f"CONTRADICTS edge written: {from_slug} -[CONTRADICTS]-> {to_slug}"


# kind -> the curator action approval performs. Coverage-shaped kinds resolve
# through `curate synth`, not approve — absence here is deliberate.
_APPROVE_ACTIONS: dict[str, Callable[[Any, dict[str, Any]], str]] = {
    "contradiction_candidate": _approve_contradiction,
}


def resolve(signal_id: str, *, approve: bool) -> ResolveResult:
    """Apply the curator's verdict to one signal."""
    with connection() as conn:
        signal = repository.get_curation_signal(conn, signal_id)
        if signal is None:
            raise ResolveError(f"no curation signal with id {signal_id}")
        status = signal["status"]
        if status not in _RESOLVABLE_STATUSES:
            raise ResolveError(
                f"signal {signal_id} is already '{status}'; only "
                f"{'/'.join(_RESOLVABLE_STATUSES)} signals can be resolved"
            )
        kind = signal["kind"]

        if not approve:
            repository.set_signal_status(conn, signal_id, "dropped")
            return ResolveResult(str(signal_id), kind, "dropped", "signal dropped")

        action = _APPROVE_ACTIONS.get(kind)
        if action is None:
            raise ResolveError(
                f"approve is not defined for kind '{kind}'; "
                "use 'compendium curate synth <signal_id>' for coverage-shaped signals"
            )
        detail = action(conn, signal)
        repository.set_signal_status(conn, signal_id, "addressed")
        return ResolveResult(str(signal_id), kind, "approved", detail)
