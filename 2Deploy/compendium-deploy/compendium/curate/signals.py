"""Slow-loop signal generators (ADR-009, Phase 9).

Each generator returns candidate signals as ``(kind, priority, payload)`` tuples.
The Postgres generator reads ``query_traces``; the graph generators read Memgraph
via ``compendium/graph/analysis.py``. The runner dedups against open signals and
inserts. Payload shapes follow ``docs/Compendium.md`` § curation schema.
"""

from __future__ import annotations

from typing import Any

import psycopg
from neo4j import Driver

from compendium.curate.signal_generator import GenerationContext, Signal, SignalGenerator
from compendium.db import repository
from compendium.graph import analysis

__all__ = [
    "GenerationContext",
    "REGISTRY",
    "Signal",
    "SignalGenerator",
    "from_contradictions",
    "from_dangling",
    "from_low_coverage",
    "from_thin_grounding",
]


def from_low_coverage(conn: psycopg.Connection, threshold: float) -> list[Signal]:
    """`low_coverage_query` signals from weak/fallback queries (one per query text)."""
    by_query: dict[str, dict[str, Any]] = {}
    for t in repository.low_coverage_traces(conn, threshold):
        q = t["query_text"]
        entry = by_query.setdefault(q, {"query_text": q, "query_trace_ids": [], "coverages": []})
        entry["query_trace_ids"].append(str(t["id"]))
        if t["coverage_score"] is not None:
            entry["coverages"].append(float(t["coverage_score"]))
    signals: list[Signal] = []
    for q, e in by_query.items():
        cov = e.pop("coverages")
        e["median_coverage"] = round(sorted(cov)[len(cov) // 2], 3) if cov else 0.0
        # Lower coverage and more repeats -> higher priority.
        priority = len(e["query_trace_ids"]) * 10 + int((1 - e["median_coverage"]) * 10)
        signals.append(Signal("low_coverage_query", priority, e))
    return signals


def from_thin_grounding(driver: Driver, min_grounds: int) -> list[Signal]:
    return [
        Signal("thin_grounding", 5 + (min_grounds - r["grounds_count"]),
               {"page_id": r["page_id"], "title": r["title"],
                "grounds_count": r["grounds_count"], "expected_threshold": min_grounds})
        for r in analysis.thin_grounding_concepts(driver, min_grounds)
    ]


def from_dangling(driver: Driver) -> list[Signal]:
    return [
        Signal("dangling_concept", 3, {"page_id": r["page_id"], "title": r["title"],
                                       "candidate_topic_ids": []})
        for r in analysis.dangling_concepts(driver)
    ]


def from_contradictions(driver: Driver) -> list[Signal]:
    return [
        Signal("unresolved_contradiction", 8,
               {"page_a": r["page_a"], "page_b": r["page_b"],
                "edge_id": f"{r['page_a']}->{r['page_b']}",
                "title_a": r["title_a"], "title_b": r["title_b"]})
        for r in analysis.unresolved_contradictions(driver)
    ]


# --- registry: the single home for the slow loop's signal generators -------
# Each entry declares its kinds + required stores; the runner iterates this and
# derives the skipped-kinds list from `kinds` (no hardcoded literal). The graph
# generators receive a non-None `ctx.driver` because the runner only calls them
# when "graph" is reachable. The extractor (ADR-010) is intentionally absent.

REGISTRY: tuple[SignalGenerator, ...] = (
    SignalGenerator(
        "low_coverage", ("low_coverage_query",), ("postgres",),
        lambda ctx: from_low_coverage(ctx.conn, ctx.low_coverage_threshold),
    ),
    SignalGenerator(
        "thin_grounding", ("thin_grounding",), ("graph",),
        lambda ctx: from_thin_grounding(ctx.driver, ctx.thin_grounding_min),
    ),
    SignalGenerator(
        "dangling", ("dangling_concept",), ("graph",),
        lambda ctx: from_dangling(ctx.driver),
    ),
    SignalGenerator(
        "contradictions", ("unresolved_contradiction",), ("graph",),
        lambda ctx: from_contradictions(ctx.driver),
    ),
)
