"""Golden dataset loader (Phase 10) + metric computation (v0.2 Phase 5).

Parses ``dataset.yaml`` into typed entries. Pure: no database, no network, no
compendium imports — just the manifest. The runner (``tests/test_golden.py``)
consumes these and seeds/queries the live corpus, then calls
:func:`compute_metrics` per query and :func:`summarize` for the aggregates.
The captured numbers live in :data:`BASELINE_PATH` and are compared back on
default runs with a small absolute tolerance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_VALID_CATEGORIES = {"A", "C", "D"}
_MANIFEST = Path(__file__).resolve().parent / "dataset.yaml"

#: Path to the captured baseline. Regenerate with ``pytest -m golden --golden-baseline``.
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"

#: Absolute tolerance for per-query and aggregate metric comparison.
BASELINE_TOLERANCE = 0.01


@dataclass
class GoldenQuery:
    """One golden query and its expectations."""

    id: str
    category: str
    query: str
    expectations: dict[str, Any]
    filters: dict[str, Any] = field(default_factory=dict)
    setup: str | None = None  # e.g. "empty_pages" to reproduce a gap hermetically


def load_dataset(path: Path | None = None) -> list[GoldenQuery]:
    """Load and validate the golden manifest."""
    raw = yaml.safe_load((path or _MANIFEST).read_text(encoding="utf-8")) or []
    queries: list[GoldenQuery] = []
    seen: set[str] = set()
    for entry in raw:
        qid = entry["id"]
        if qid in seen:
            raise ValueError(f"duplicate golden query id: {qid}")
        seen.add(qid)
        category = entry["category"]
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"{qid}: unknown category {category!r}")
        if not entry.get("query") or "expectations" not in entry:
            raise ValueError(f"{qid}: missing query or expectations")
        queries.append(
            GoldenQuery(
                id=qid,
                category=category,
                query=entry["query"],
                expectations=entry["expectations"],
                filters=entry.get("filters") or {},
                setup=entry.get("setup"),
            )
        )
    return queries


# --- v0.2 Phase 5: metric computation -------------------------------------


def _top_k() -> int:
    """Read ``retrieval.top_k`` from ``config/settings.yaml`` (default 7)."""
    from compendium.config import load_config

    return load_config().settings.get("retrieval", {}).get("top_k", 7)


def compute_metrics(result: Any, query: GoldenQuery, k: int | None = None) -> dict:
    """Compute ``coverage_score``, ``recall_at_k``, and ``mrr`` for one query.

    ``recall_at_k`` and ``mrr`` are ``None`` when the query expectation
    carries no ``must_include_slug`` (Categories C and D in v0.1's golden
    manifest). ``coverage_score`` is always populated from the retrieval
    result.
    """
    if k is None:
        k = _top_k()
    expectation = query.expectations
    must_include = expectation.get("must_include_slug")
    page_slugs = [p.slug for p in (result.pages or [])]

    recall_at_k: float | None = None
    mrr: float | None = None
    if must_include is not None:
        top = page_slugs[:k]
        recall_at_k = 1.0 if must_include in top else 0.0
        if must_include in top:
            rank = top.index(must_include) + 1
            mrr = 1.0 / rank
        else:
            mrr = 0.0

    return {
        "coverage_score": float(result.coverage_score or 0.0),
        "recall_at_k": recall_at_k,
        "mrr": mrr,
    }


def _mean(values: list[float]) -> float | None:
    """Mean ignoring ``None``. Returns ``None`` when no defined value."""
    defined = [v for v in values if v is not None]
    return sum(defined) / len(defined) if defined else None


def summarize(per_query: dict[str, dict]) -> dict:
    """Aggregate per-query metrics into per-category and overall means.

    Input: ``{query_id: {coverage_score, recall_at_k, mrr}}``.
    Output: ``{by_category: {A: {...}, C: {...}, D: {...}}, overall: {...}}``.
    Means are computed only over queries where the metric is defined
    (``None`` values are excluded, not coerced to 0).
    """
    dataset = {q.id: q for q in load_dataset()}
    by_category: dict[str, dict[str, list]] = defaultdict(
        lambda: {"coverage_score": [], "recall_at_k": [], "mrr": []}
    )
    overall = {"coverage_score": [], "recall_at_k": [], "mrr": []}
    for qid, metrics in per_query.items():
        category = dataset[qid].category
        for key in ("coverage_score", "recall_at_k", "mrr"):
            by_category[category][key].append(metrics[key])
            overall[key].append(metrics[key])

    def _agg(buckets: dict[str, list]) -> dict[str, float | None]:
        return {key: _mean(values) for key, values in buckets.items()}

    return {
        "by_category": {cat: _agg(buckets) for cat, buckets in by_category.items()},
        "overall": _agg(overall),
    }


def compare_to_baseline(
    live: dict, baseline: dict, tolerance: float = BASELINE_TOLERANCE
) -> list[str]:
    """Return a list of regression messages (empty when nothing regressed).

    A metric regresses when ``baseline_value - live_value > tolerance`` AND
    the baseline value is defined. Improvements are not flagged. Per-query
    and aggregate paths are both checked.
    """
    fails: list[str] = []

    def _check(path: str, live_val: Any, base_val: Any) -> None:
        if base_val is None or live_val is None:
            return
        delta = base_val - live_val
        if delta > tolerance:
            fails.append(
                f"{path}: live={live_val:.4f} baseline={base_val:.4f} "
                f"delta=-{delta:.4f} (> {tolerance})"
            )

    # Per-query comparisons.
    for qid, metrics in live.get("per_query", {}).items():
        base_q = baseline.get("per_query", {}).get(qid)
        if base_q is None:
            continue
        for key in ("coverage_score", "recall_at_k", "mrr"):
            _check(f"per_query[{qid}].{key}", metrics.get(key), base_q.get(key))

    # Aggregate comparisons.
    live_by_cat = live.get("by_category", {})
    base_by_cat = baseline.get("by_category", {})
    for category in sorted(set(live_by_cat) | set(base_by_cat)):
        for key in ("coverage_score", "recall_at_k", "mrr"):
            _check(
                f"by_category[{category}].{key}",
                live_by_cat.get(category, {}).get(key),
                base_by_cat.get(category, {}).get(key),
            )
    for key in ("coverage_score", "recall_at_k", "mrr"):
        _check(
            f"overall.{key}",
            live.get("overall", {}).get(key),
            baseline.get("overall", {}).get(key),
        )
    return fails
