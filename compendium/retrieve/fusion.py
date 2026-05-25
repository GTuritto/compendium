"""Reciprocal rank fusion (ADR-003 step 4).

The OpenSearch (BM25) and Qdrant (cosine) score scales are incomparable, so
fusion is on *rank*, not score. A candidate's fused score is the sum, over the
ranked lists that contain it, of ``1 / (rrf_k + rank)`` with 1-based rank. This
is scale-free and reproducible for a fixed corpus revision. Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compendium.retrieve.search import Hit


@dataclass
class FusedHit:
    """A fused candidate: entity id, summed RRF score, contributing ranks, fields."""

    entity_id: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[Hit]], rrf_k: int = 60
) -> list[FusedHit]:
    """Fuse named ranked lists into one list ordered by descending RRF score.

    Args:
        ranked_lists: retriever name -> its ordered Hits (best first).
        rrf_k: the RRF constant (config ``retrieval.rrf_k``, default 60).

    Ties in fused score break by entity id, so the order is deterministic.
    """
    fused: dict[str, FusedHit] = {}
    for retriever, hits in ranked_lists.items():
        for rank, hit in enumerate(hits, start=1):
            entry = fused.get(hit.entity_id)
            if entry is None:
                entry = FusedHit(entity_id=hit.entity_id, score=0.0)
                fused[hit.entity_id] = entry
            entry.score += 1.0 / (rrf_k + rank)
            entry.ranks[retriever] = rank
            # First retriever to carry fields wins; they describe the same entity.
            if not entry.fields and hit.fields:
                entry.fields = hit.fields
    return sorted(fused.values(), key=lambda f: (-f.score, f.entity_id))
