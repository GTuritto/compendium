"""The single home for the slow-loop signal-generator contract (ADR-009).

A `SignalGenerator` record declares, per generator, the signal `kinds` it emits,
the stores it `requires`, and how it generates from a `GenerationContext`. The
runner (`curate/run.py`) iterates a registry of these instead of hardwiring the
call sequence and restating the kinds as a literal — the same strategy-registry
shape as `graph/edge_type.py` and `wiki/page_kind.py`.

Types live here (no imports from `signals.py`); the registry and the generator
bodies live in `signals.py`, which imports these. The autonomous edge extractor
(`from_extracted_edges`, ADR-010) is deliberately NOT a `SignalGenerator` — it
writes edges and returns counts, not signals — and stays a separate run step.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    import psycopg
    from neo4j import Driver


class Signal(NamedTuple):
    """A candidate curation signal. Unpacks as ``(kind, priority, payload)`` and
    compares equal to that plain tuple, so existing call sites are unaffected."""

    kind: str
    priority: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class GenerationContext:
    """The stores and tuned thresholds a generator reads. ``driver`` is non-None
    only when Memgraph is reachable (graph generators require it)."""

    conn: "psycopg.Connection"
    driver: "Driver | None"
    thin_grounding_min: int
    low_coverage_threshold: float


@dataclass(frozen=True)
class SignalGenerator:
    """One slow-loop signal generator and the rules that govern it.

    - ``kinds``: the signal kinds it can emit (the source for the run's
      skipped-kinds list — no hardcoded literal in the runner).
    - ``requires``: the stores it needs, a subset of ``{"postgres", "graph"}``;
      the runner skips the generator (recording its ``kinds``) when any is
      unreachable.
    - ``generate``: produces candidate signals from a `GenerationContext`.
    """

    name: str
    kinds: tuple[str, ...]
    requires: tuple[str, ...]
    generate: Callable[["GenerationContext"], list[Signal]]
