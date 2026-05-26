"""The on-demand slow loop (ADR-009, Phase 9): ``compendium curate run``.

One analysis pass: open a ``graph_analysis_runs`` row, run the signal
generators (the graph-backed ones skipped gracefully when Memgraph is down),
dedup against currently-open signals, insert the new ones, and complete the run
with a count and a per-kind summary. No daemon — operator-triggered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compendium.config import load_config
from compendium.curate import signals as gen
from compendium.db import repository
from compendium.db.connection import connection


@dataclass
class CurateReport:
    run_id: str
    inserted: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    skipped_generators: list[str] = field(default_factory=list)


def _curation_cfg() -> tuple[int, float]:
    c = load_config().settings.get("curation", {})
    return int(c.get("thin_grounding_min", 2)), float(c.get("low_coverage_threshold", 0.5))


def run() -> CurateReport:
    """Run one slow-loop pass and return what it produced."""
    thin_min, low_cov = _curation_cfg()

    with connection() as conn:
        run_id = repository.open_analysis_run(conn)
        candidates: list[gen.Signal] = list(gen.from_low_coverage(conn, low_cov))
        skipped: list[str] = []

        # Graph-backed generators: skip gracefully if Memgraph is unreachable.
        from compendium.graph.client import graph_connection, graph_reachable

        graph_kinds = ["thin_grounding", "dangling_concept", "unresolved_contradiction"]
        with graph_connection() as driver:
            try:
                if graph_reachable(driver):
                    candidates += gen.from_thin_grounding(driver, thin_min)
                    candidates += gen.from_dangling(driver)
                    candidates += gen.from_contradictions(driver)
                else:
                    skipped = list(graph_kinds)
            except Exception:  # a graph query failed; keep the Postgres signals
                skipped = list(graph_kinds)

        open_keys = repository.open_signal_keys(conn)
        report = CurateReport(run_id=str(run_id), skipped_generators=skipped)
        for kind, priority, payload in candidates:
            key = (kind, repository._signal_dedup_key(payload))
            if key in open_keys:
                continue
            repository.insert_curation_signal(
                conn, kind=kind, priority=priority, payload=payload, run_id=run_id
            )
            open_keys.add(key)
            report.inserted += 1
            report.by_kind[kind] = report.by_kind.get(kind, 0) + 1

        summary: dict[str, Any] = {"by_kind": report.by_kind, "skipped": skipped}
        repository.complete_analysis_run(
            conn, run_id, signal_count=report.inserted, summary=summary
        )
    return report
