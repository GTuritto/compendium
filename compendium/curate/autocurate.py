"""Curation autonomy modes (ADR-022, amends ADR-009).

A knob over the slow loop's concept synthesis/promotion — and only that
(autonomous edge extraction, ADR-010, and CONTRADICTS candidates, ADR-014, are
untouched):

- **manual** — no auto-drafting; the loop only surfaces signals (pre-knob).
- **semi-auto** (default) — draft concept pages from eligible signals as DRAFT
  pages; the curator approves (promotes) what becomes canonical.
- **auto** (opt-in, off by default) — draft, self-review, and promote drafts
  above a confidence threshold; ``shadow`` drafts without promoting.

Guardrails: a target whose concept page already exists and is NOT a synth draft
(curator-authored or already canonical) is never overwritten; drafts carry the
synthesizer's ``generator=synth`` / ``status=draft`` marker and a revision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from compendium.db import repository
from compendium.wiki.slug import slugify

# Signal kinds an eligible draft can be derived from (concept-shaped).
_DRAFTABLE = {"low_coverage_query", "gap", "thin_grounding", "dangling_concept"}


@dataclass
class AutocurateReport:
    mode: str
    drafted: int = 0
    promoted: int = 0
    skipped: int = 0


def autocurate(
    conn,
    signal_ids: list[str],
    *,
    mode: str,
    vault_path: str,
    shadow: bool = False,
    max_drafts: int = 10,
    confidence: float = 0.8,
) -> AutocurateReport:
    """Draft (semi-auto) and optionally promote (auto) concept pages from the
    given signals. ``manual`` is a no-op."""
    report = AutocurateReport(mode=mode)
    if mode == "manual":
        return report

    from compendium.curate.synth import _target_name, synth_from_signal
    from compendium.trace.promote import promote

    for sid in signal_ids:
        if report.drafted >= max_drafts:
            break
        signal = repository.get_curation_signal(conn, sid)
        if signal is None or signal["kind"] not in _DRAFTABLE:
            continue
        try:
            name = _target_name(signal)
        except Exception:
            report.skipped += 1
            continue
        slug = slugify(name)
        # C4: never overwrite an existing concept page (the synthesizer would
        # update it in place). Autocuration only creates brand-new drafts.
        if repository.get_wiki_page_by_slug(conn, "concept", slug) is not None:
            report.skipped += 1
            continue
        if shadow:
            report.drafted += 1
            continue
        try:
            page_slug = synth_from_signal(sid)
        except Exception:
            report.skipped += 1
            continue
        report.drafted += 1
        if mode == "auto" and _self_review(name) >= confidence:
            try:
                promote(
                    page_slug, "canonical", vault_path=vault_path,
                    notes="auto-curated (ADR-022)",
                )
                report.promoted += 1
            except Exception:  # promotion is best-effort; the draft remains
                pass
    return report


def _self_review(name: str) -> float:
    """LLM-as-judge gate for auto-promotion; returns a confidence in [0, 1].

    Stub-friendly: under the synth stub it passes (1.0) so the hermetic tier is
    deterministic. With a real model it asks the answerer for a YES/NO verdict.
    """
    if os.getenv("COMPENDIUM_SYNTH_STUB") == "1":
        return 1.0
    try:
        from compendium.answer.llm import get_answerer

        verdict = get_answerer().compose(
            f"Is '{name}' a coherent, well-grounded concept worth keeping in a "
            "knowledge wiki? Answer YES or NO.",
            "",
        )
        return 1.0 if "YES" in (verdict.text or "").upper() else 0.0
    except Exception:
        return 0.0
