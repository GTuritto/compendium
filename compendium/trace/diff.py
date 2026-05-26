"""Ranking diff for trace replay (ADR-007).

Pure functions: compare a stored trace's ``final_ranking`` against a freshly
replayed one and report what a reader would notice — pages added, removed, or
moved in rank — plus the coverage and fallback deltas. The full per-stage
pipeline stays in ``trace show``; this is the user-visible answer diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RankingDiff:
    """What changed between an original and a replayed ranking."""

    added: list[dict[str, Any]] = field(default_factory=list)      # in new, not old
    removed: list[dict[str, Any]] = field(default_factory=list)    # in old, not new
    moved: list[dict[str, Any]] = field(default_factory=list)      # rank changed
    coverage_delta: float = 0.0
    fallback_changed: bool = False

    @property
    def unchanged(self) -> bool:
        return not (self.added or self.removed or self.moved) and not self.fallback_changed


def _rank_map(ranking: list[dict[str, Any]]) -> dict[str, int]:
    return {row["entity_id"]: i for i, row in enumerate(ranking, start=1)}


def _title(ranking: list[dict[str, Any]], entity_id: str) -> str:
    for row in ranking:
        if row["entity_id"] == entity_id:
            return row.get("title", "")
    return ""


def ranking_diff(
    original: list[dict[str, Any]],
    replayed: list[dict[str, Any]],
    *,
    original_coverage: float | None = None,
    replayed_coverage: float | None = None,
    original_fallback: bool | None = None,
    replayed_fallback: bool | None = None,
) -> RankingDiff:
    """Diff two ``final_ranking`` lists (each row has entity_id/title/...)."""
    old_ranks = _rank_map(original)
    new_ranks = _rank_map(replayed)

    diff = RankingDiff()
    for entity_id, new_rank in new_ranks.items():
        if entity_id not in old_ranks:
            diff.added.append(
                {"entity_id": entity_id, "title": _title(replayed, entity_id),
                 "rank": new_rank}
            )
    for entity_id, old_rank in old_ranks.items():
        if entity_id not in new_ranks:
            diff.removed.append(
                {"entity_id": entity_id, "title": _title(original, entity_id),
                 "rank": old_rank}
            )
        elif new_ranks[entity_id] != old_rank:
            diff.moved.append(
                {"entity_id": entity_id, "title": _title(original, entity_id),
                 "from_rank": old_rank, "to_rank": new_ranks[entity_id]}
            )

    diff.moved.sort(key=lambda m: m["to_rank"])
    diff.added.sort(key=lambda a: a["rank"])
    diff.removed.sort(key=lambda r: r["rank"])

    if original_coverage is not None and replayed_coverage is not None:
        diff.coverage_delta = replayed_coverage - original_coverage
    if original_fallback is not None and replayed_fallback is not None:
        diff.fallback_changed = original_fallback != replayed_fallback
    return diff
