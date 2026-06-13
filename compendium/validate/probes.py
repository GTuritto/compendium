"""The probe set: real questions, curated, frozen, kept outside the repo.

A probe set is the durable instrument the A/B harness replays for the life of
the project (distinct from the synthetic golden set). ``harvest`` lists
distinct real questions from ``ask_traces`` as candidates; the curator prunes
them, labels each with the relevant page slugs, marks the file ``frozen:
true``, and stores it under ``~/.compendium/probes/`` by default. Real
personal queries must never land in ``tests/`` or the 2Deploy bundle.

Probe-set YAML shape::

    frozen: true
    probes:
      - id: psych-safety-basics
        query: "what is psychological safety"
        expected: [psychological-safety]      # relevant page slugs
        notes: "asked 2026-06-12"

``harvest`` candidates are the same shape with ``frozen: false`` and empty
``expected`` for the curator to fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def default_probe_dir() -> Path:
    """``~/.compendium/probes`` — outside the repo by design."""
    return Path.home() / ".compendium" / "probes"


@dataclass
class Probe:
    """One frozen probe: a real query and its curator-labelled relevant pages."""

    id: str
    query: str
    expected: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass
class ProbeSet:
    """A frozen set of probes. ``run`` refuses anything not ``frozen``."""

    frozen: bool
    probes: list[Probe]


class ProbeSetError(RuntimeError):
    """A probe set could not be loaded or is not frozen."""


def load_probe_set(path: str | Path) -> ProbeSet:
    """Load and validate a frozen probe set.

    Raises ``ProbeSetError`` when the file is missing the ``frozen: true``
    guard (the runner must never measure against an unfrozen, still-editing
    set) or carries no probes.
    """
    p = Path(path)
    if not p.exists():
        raise ProbeSetError(f"probe set not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not raw.get("frozen"):
        raise ProbeSetError(
            f"{p} is not frozen — set 'frozen: true' once the probe set is "
            "curated and final before running a measurement against it"
        )
    entries = raw.get("probes") or []
    if not entries:
        raise ProbeSetError(f"{p} has no probes")
    probes = [
        Probe(
            id=e["id"],
            query=e["query"],
            expected=list(e.get("expected") or []),
            notes=e.get("notes"),
        )
        for e in entries
    ]
    return ProbeSet(frozen=True, probes=probes)


def harvest_candidates(limit: int = 200) -> list[dict[str, Any]]:
    """Distinct real questions from ``ask_traces``, newest first, as candidates.

    Each candidate is the probe shape with ``expected: []`` for the curator to
    label. Reads only; writes nothing.
    """
    from compendium.db import repository
    from compendium.db.connection import connection

    with connection() as conn:
        rows = repository.distinct_ask_questions(conn, limit=limit)

    candidates: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        candidates.append(
            {
                "id": f"probe-{i:03d}",
                "query": row["query_text"],
                "expected": [],
                "notes": f"asked {row['asked_at']}",
            }
        )
    return candidates


def dump_candidates(candidates: list[dict[str, Any]]) -> str:
    """A candidate probe-set YAML (``frozen: false``) for the curator to edit."""
    return yaml.safe_dump(
        {"frozen": False, "probes": candidates},
        sort_keys=False,
        allow_unicode=True,
    )
