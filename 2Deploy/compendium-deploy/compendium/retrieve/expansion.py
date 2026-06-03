"""Fast-loop graph expansion (ADR-009, Phase 9).

After RRF fusion, walk semantic edges from the top seed pages and score each
reached page off the strength of the seed that reached it:

    expansion_score = seed_fused_score * weight * decay^(hop - 1)

so an expanded page contributes at most ``weight`` of its seed's score and never
outranks a strong direct hit. Scoring/merge is pure; the graph walk is the only
I/O (run in a worker thread by the caller, since the graph client is sync).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExpansionOutcome:
    """Reached pages (scored) and the trace payload for graph_expansion."""

    reached: list[dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] | None = None


def score_reached(
    seed_scores: dict[str, float],
    walk_rows: list[dict[str, Any]],
    *,
    decay: float,
    weight: float,
) -> ExpansionOutcome:
    """Score walk rows into reached pages (best score per page id). Pure."""
    best: dict[str, dict[str, Any]] = {}
    for row in walk_rows:
        seed_score = seed_scores.get(row["seed_id"], 0.0)
        hop = int(row["hop"])
        score = seed_score * weight * (decay ** (hop - 1))
        existing = best.get(row["id"])
        if existing is None or score > existing["score"]:
            best[row["id"]] = {
                "entity_id": row["id"],
                "title": row.get("title") or "",
                "slug": row.get("slug") or "",
                "kind": row.get("kind") or "",
                "hop": hop,
                "seed_id": row["seed_id"],
                "score": score,
            }
    reached = sorted(best.values(), key=lambda r: (-r["score"], r["entity_id"]))
    if not reached:
        return ExpansionOutcome(reached=[], payload=None)
    payload = {
        "seeds": list(seed_scores.keys()),
        "reached": [
            {"entity_id": r["entity_id"], "title": r["title"], "hop": r["hop"],
             "seed_id": r["seed_id"], "score": r["score"]}
            for r in reached
        ],
    }
    return ExpansionOutcome(reached=reached, payload=payload)


def expand(
    seed_scores: dict[str, float],
    *,
    max_hops: int,
    decay: float,
    weight: float,
) -> ExpansionOutcome:
    """Walk semantic edges from the seeds and score the reached pages.

    Returns an empty outcome (payload None) when Memgraph is unreachable or
    nothing is reached, so the caller leaves the base ranking unchanged.
    """
    from compendium.graph import browse
    from compendium.graph.client import graph_connection, graph_reachable

    with graph_connection() as driver:
        if not graph_reachable(driver):
            return ExpansionOutcome(reached=[], payload=None)
        try:
            rows = browse.walk_semantic(driver, list(seed_scores.keys()), max_hops)
        except Exception:
            return ExpansionOutcome(reached=[], payload=None)
    return score_reached(seed_scores, rows, decay=decay, weight=weight)
