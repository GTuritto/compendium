"""Trace replay (ADR-007).

Load a stored trace, re-run its query text against the current corpus through
the Phase 5 retrieval pipeline, and diff the result against the original. Replay
is read-only by default (``persist=False`` — it writes no new ``query_traces``
row), which keeps the table clean for the Phase 10 CI regression check; pass
``persist=True`` to record the replay as a fresh trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from compendium.db import repository
from compendium.db.connection import connection
from compendium.retrieve.pipeline import query as run_query
from compendium.trace.diff import RankingDiff, ranking_diff


@dataclass
class ReplayResult:
    """A replayed trace: the original trace row, the fresh result, and the diff."""

    trace_id: str
    query_text: str
    original_coverage: float | None
    replayed_coverage: float
    diff: RankingDiff


class TraceNotFound(Exception):
    """Raised when the trace id does not exist."""


def replay(trace_id: str, *, persist: bool = False) -> ReplayResult:
    """Re-run a stored trace's query and diff it against the original."""
    with connection() as conn:
        trace = repository.get_query_trace(conn, trace_id)
    if trace is None:
        raise TraceNotFound(trace_id)

    original_ranking: list[dict[str, Any]] = trace["final_ranking"] or []
    original_coverage = (
        float(trace["coverage_score"]) if trace["coverage_score"] is not None else None
    )
    original_fallback = trace["fallback_to_chunks"]

    result = run_query(trace["query_text"], persist=persist)
    replayed_ranking = result.trace["final_ranking"]

    diff = ranking_diff(
        original_ranking,
        replayed_ranking,
        original_coverage=original_coverage,
        replayed_coverage=result.coverage_score,
        original_fallback=original_fallback,
        replayed_fallback=result.fallback_to_chunks,
    )
    return ReplayResult(
        trace_id=str(trace["id"]),
        query_text=trace["query_text"],
        original_coverage=original_coverage,
        replayed_coverage=result.coverage_score,
        diff=diff,
    )
