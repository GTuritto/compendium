"""The on-demand slow loop (ADR-009, Phase 9): ``compendium curate run``.

One analysis pass: open a ``graph_analysis_runs`` row, run the signal
generators (the graph-backed ones skipped gracefully when Memgraph is down),
dedup against currently-open signals, insert the new ones, and complete the run
with a count and a per-kind summary. No daemon — operator-triggered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compendium import config_sections
from compendium.curate import signals as gen
from compendium.db import repository
from compendium.db.connection import connection


@dataclass
class CurateReport:
    run_id: str
    inserted: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    skipped_generators: list[str] = field(default_factory=list)
    extracted_edges: dict[str, int] = field(default_factory=dict)
    contradictions: dict[str, int] = field(default_factory=dict)


def _curation_cfg() -> tuple[int, float]:
    c = config_sections.curation()
    return c["thin_grounding_min"], c["low_coverage_threshold"]


def run() -> CurateReport:
    """Run one slow-loop pass and return what it produced."""
    thin_min, low_cov = _curation_cfg()

    with connection() as conn:
        run_id = repository.open_analysis_run(conn)
        candidates: list[gen.Signal] = []
        skipped: list[str] = []

        from compendium.curate import contradict, extract
        from compendium.graph.client import graph_connection, graph_reachable

        extracted: dict[str, int] = {}
        contradictions: dict[str, int] = {}
        with graph_connection() as driver:
            graph_up = graph_reachable(driver)
            ctx = gen.GenerationContext(
                conn=conn, driver=driver,
                thin_grounding_min=thin_min, low_coverage_threshold=low_cov,
            )
            reachable = {"postgres"} | ({"graph"} if graph_up else set())

            # Iterate the registry: skip a generator (recording its kinds) when a
            # required store is unreachable or its query raises. The skipped-kinds
            # list derives from each generator's `kinds` — no hardcoded literal.
            for g in gen.REGISTRY:
                if not set(g.requires) <= reachable:
                    skipped.extend(g.kinds)
                    continue
                try:
                    candidates += g.generate(ctx)
                except Exception:  # this generator's query failed; keep the rest
                    skipped.extend(g.kinds)

            # Autonomous edge extraction (ADR-010): a separate step, not a signal
            # generator. Needs Memgraph + Qdrant.
            ecfg = extract.extract_cfg()
            if ecfg["enabled"] and graph_up:
                from compendium.index.clients import qdrant_client, qdrant_reachable

                qc = qdrant_client()
                if qdrant_reachable(qc):
                    try:
                        extracted = extract.from_extracted_edges(conn, driver, qc, ecfg).as_dict()
                    except Exception:  # extraction is best-effort; keep the run
                        skipped.append("extracted_edges")
                else:
                    skipped.append("extracted_edges")

            # Contradiction candidates (ADR-014): the second separate step.
            # Proposes signals only; the curator's resolve writes any edge.
            ccfg = contradict.contradict_cfg()
            if ccfg["enabled"] and graph_up:
                from compendium.index.clients import qdrant_client, qdrant_reachable

                qc = qdrant_client()
                if qdrant_reachable(qc):
                    try:
                        creport = contradict.from_contradiction_candidates(
                            conn, driver, qc, ccfg, run_id=run_id
                        )
                        contradictions = creport.as_dict()
                    except Exception:  # best-effort; keep the run
                        skipped.append("contradiction_candidate")
                else:
                    skipped.append("contradiction_candidate")

        open_keys = repository.open_signal_keys(conn)
        report = CurateReport(
            run_id=str(run_id), skipped_generators=skipped,
            extracted_edges=extracted, contradictions=contradictions,
        )
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

        summary: dict[str, Any] = {
            "by_kind": report.by_kind, "skipped": skipped,
            "extracted_edges": extracted, "contradictions": contradictions,
        }
        repository.complete_analysis_run(
            conn, run_id, signal_count=report.inserted, summary=summary
        )
    return report
