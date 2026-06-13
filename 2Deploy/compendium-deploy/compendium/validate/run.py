"""The single-point A/B runner (ADR-016).

Runs each probe through both retrieval arms — page-first and the chunk-only
control — against the current corpus state, in one process, with Qdrant exact
search for repeatability, and reports the per-query page-space delta. The
report carries a methodology header naming the three pre-registered decisions
so any saved report is self-describing.

This module is the only caller of the pipeline's ``arm="chunks"`` control arm.
"""

from __future__ import annotations

from typing import Any

from compendium.retrieve import pipeline
from compendium.validate import metrics
from compendium.validate.probes import Probe, ProbeSet

# The pre-registered measurement decisions (ADR-016). Stamped into every report.
METHODOLOGY = {
    "scoring_unit": "page (a chunk credits its parent source page)",
    "normalization": "applied to both arms (wiki-derived aliases; conservative)",
    "search": "Qdrant exact kNN for measurement; production keeps HNSW",
}


def _top_k() -> int:
    from compendium import config_sections

    return config_sections.retrieval()["top_k"]


def _chunk_ranking_pages(result: Any) -> list[str]:
    """Reduce the control arm's chunk citations to parent source-page slugs.

    One batched DB join (``source_page_slugs_for_chunks``); chunks whose source
    has no source page drop out. Order is preserved so MRR is meaningful.
    """
    chunk_ids = [c.entity_id for c in (result.citations or [])]
    if not chunk_ids:
        return []
    from compendium.db import repository
    from compendium.db.connection import connection

    with connection() as conn:
        mapping = repository.source_page_slugs_for_chunks(conn, chunk_ids)
    return [mapping[cid] for cid in chunk_ids if cid in mapping]


def _run_probe(probe: Probe, k: int) -> dict[str, Any]:
    """Both arms for one probe; per-arm page-space metrics and the delta."""
    page_result = pipeline.query(probe.query, arm="pages", exact=True)
    chunk_result = pipeline.query(probe.query, arm="chunks", exact=True)

    page_ranking = metrics.page_slugs_from_pages(page_result)
    chunk_ranking = _chunk_ranking_pages(chunk_result)

    page_metrics = metrics.score(page_ranking, probe.expected, k)
    chunk_metrics = metrics.score(chunk_ranking, probe.expected, k)
    missing = [s for s in probe.expected if s not in set(page_ranking) | set(chunk_ranking)]

    return {
        "id": probe.id,
        "query": probe.query,
        "expected": probe.expected,
        "page": page_metrics,
        "chunk": chunk_metrics,
        "delta": metrics.delta(page_metrics, chunk_metrics),
        "unresolved_expected": missing,
    }


def run_ab(probe_set: ProbeSet, *, k: int | None = None) -> dict[str, Any]:
    """Run every probe through both arms; return the comparison report.

    Deterministic given a fixed corpus state (exact search). The report is a
    plain dict: ``methodology`` header, ``k``, ``per_query`` rows, and the
    ``aggregate`` means + delta. Callers stamp any timestamp themselves.
    """
    if k is None:
        k = _top_k()
    per_query = [_run_probe(p, k) for p in probe_set.probes]
    return {
        "methodology": METHODOLOGY,
        "k": k,
        "per_query": per_query,
        "aggregate": metrics.aggregate(per_query),
    }
