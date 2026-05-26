"""Synth-from-signal (ADR-009, Phase 9).

Derive a synthesis target from a curation signal's payload and run the existing
Phase 3 synthesizer to produce a draft concept page, moving the signal to
``in_progress``. The promotion side (marking the signal ``addressed`` and adding
``SYNTHESIZES`` edges) lives in the Phase 7 ``promote`` path, extended in 9c.
"""

from __future__ import annotations

from compendium.config import load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.wiki.synth import SynthesisError, synthesize_concept


class SignalNotFound(Exception):
    """Raised when the signal id does not exist."""


class SynthError(Exception):
    """Raised when synthesis from a signal fails."""


def _target_name(signal: dict) -> str:
    """The concept name to synthesize, derived from the signal payload."""
    payload = signal["payload"]
    kind = signal["kind"]
    if kind in ("low_coverage_query", "gap"):
        missing = payload.get("missing_concepts")
        if missing:
            return missing[0]
        return payload["query_text"]
    # page-keyed kinds (thin_grounding / dangling_concept): re-synthesize the page
    if payload.get("title"):
        return payload["title"]
    raise SynthError(f"cannot derive a synth target from a {kind} signal")


def synth_from_signal(signal_id: str) -> str:
    """Synthesize a draft from a signal; return the page slug. Signal -> in_progress."""
    vault = load_config().vault_path
    with connection() as conn:
        signal = repository.get_curation_signal(conn, signal_id)
        if signal is None:
            raise SignalNotFound(signal_id)
        name = _target_name(signal)
        try:
            page = synthesize_concept(conn, name, aliases=[], vault_path=vault)
        except SynthesisError as exc:
            raise SynthError(str(exc)) from exc
        repository.set_signal_status(conn, signal_id, "in_progress")
    return page.slug
