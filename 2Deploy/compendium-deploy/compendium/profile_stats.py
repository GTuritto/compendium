"""Read-only performance stats for ``compendium profile stats``.

On-demand aggregation over what the system already persists: query_traces
(per-stage latencies, coverage, fallback), ask_traces (tokens, cost,
refusals), graph_analysis_runs (curate-run durations), index_sync_state /
v_sync_lag (backlog and failures), and sources (ingest outcomes plus the
``stage_ms`` durations captured at ingest). No write path, no new storage;
the repository functions this module calls are all plain SELECTs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compendium.db import repository
from compendium.db.connection import connection


@dataclass
class ProfileStatsReport:
    """One ``profile stats`` aggregation, ready to render as text or JSON."""

    days: int
    by: str | None
    retrieval: dict[str, Any] = field(default_factory=dict)
    retrieval_stages: list[dict[str, Any]] = field(default_factory=list)
    retrieval_per_day: list[dict[str, Any]] = field(default_factory=list)
    retrieval_grouped: list[dict[str, Any]] = field(default_factory=list)
    ask: dict[str, Any] = field(default_factory=dict)
    ask_by_model: list[dict[str, Any]] = field(default_factory=list)
    curate: dict[str, Any] = field(default_factory=dict)
    sync: dict[str, Any] = field(default_factory=dict)
    ingest_outcomes: list[dict[str, Any]] = field(default_factory=list)
    ingest_stages: list[dict[str, Any]] = field(default_factory=list)


def gather(days: int = 30, by: str | None = None) -> ProfileStatsReport:
    """Aggregate the window's performance stats from PostgreSQL, read-only."""
    with connection() as conn:
        report = ProfileStatsReport(
            days=days,
            by=by,
            retrieval=dict(repository.retrieval_summary_stats(conn, days)),
            retrieval_stages=repository.retrieval_stage_stats(conn, days),
            retrieval_per_day=repository.retrieval_per_day(conn, days),
            ask=dict(repository.ask_summary_stats(conn, days)),
            ask_by_model=repository.ask_by_model_stats(conn, days),
            curate=dict(repository.curate_run_stats(conn, days)),
            sync=repository.sync_backlog_stats(conn),
            ingest_outcomes=repository.ingest_outcome_stats(conn, days),
            ingest_stages=repository.ingest_stage_stats(conn, days),
        )
        if by is not None:
            report.retrieval_grouped = repository.retrieval_grouped_stats(
                conn, days, by
            )
    return report
