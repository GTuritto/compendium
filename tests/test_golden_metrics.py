"""Unit tests for the v0.2 Phase 5 golden metric helpers.

These are pure-Python tests with no DB and no live retrieval — they exercise
``compute_metrics``, ``summarize``, and ``compare_to_baseline`` against
hand-built ``GoldenQuery`` and result fixtures.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.golden import (
    BASELINE_TOLERANCE,
    GoldenQuery,
    compare_to_baseline,
    compute_metrics,
    summarize,
)


def _result(pages: list[str], coverage: float = 0.5):
    """Build a minimal retrieval-result stand-in: just `.pages` and `.coverage_score`."""
    page_objs = [SimpleNamespace(slug=slug) for slug in pages]
    return SimpleNamespace(pages=page_objs, coverage_score=coverage)


def _query(qid: str, category: str, must_include: str | None = None) -> GoldenQuery:
    expectations: dict = {}
    if must_include is not None:
        expectations["must_include_slug"] = must_include
    return GoldenQuery(id=qid, category=category, query="x", expectations=expectations)


# --- compute_metrics ------------------------------------------------------


def test_compute_metrics_rank_one_is_perfect() -> None:
    q = _query("q1", "A", must_include="psychological-safety")
    result = _result(["psychological-safety", "other"], coverage=0.78)
    m = compute_metrics(result, q, k=7)
    assert m == {"coverage_score": 0.78, "recall_at_k": 1.0, "mrr": 1.0}


def test_compute_metrics_rank_two_halves_mrr() -> None:
    q = _query("q1", "A", must_include="psychological-safety")
    result = _result(["other", "psychological-safety"], coverage=0.5)
    m = compute_metrics(result, q, k=7)
    assert m["recall_at_k"] == 1.0
    assert m["mrr"] == 0.5


def test_compute_metrics_missing_from_top_k_zero() -> None:
    q = _query("q1", "A", must_include="not-here")
    result = _result(["a", "b", "c"], coverage=0.2)
    m = compute_metrics(result, q, k=3)
    assert m["recall_at_k"] == 0.0
    assert m["mrr"] == 0.0


def test_compute_metrics_outside_k_is_zero_even_if_in_pages() -> None:
    """A page beyond top-K does not count for recall@K or MRR."""
    q = _query("q1", "A", must_include="needle")
    result = _result(["a", "b", "c", "needle"], coverage=0.4)
    m = compute_metrics(result, q, k=3)
    assert m["recall_at_k"] == 0.0
    assert m["mrr"] == 0.0


def test_compute_metrics_no_must_include_returns_null() -> None:
    q = _query("q_c", "C", must_include=None)
    result = _result(["a", "b"], coverage=0.0)
    m = compute_metrics(result, q, k=7)
    assert m["coverage_score"] == 0.0
    assert m["recall_at_k"] is None
    assert m["mrr"] is None


def test_compute_metrics_coverage_score_passthrough() -> None:
    q = _query("q1", "A", must_include="x")
    result = _result(["x"], coverage=0.7849)
    m = compute_metrics(result, q, k=7)
    # Coverage rides through verbatim, not rounded.
    assert m["coverage_score"] == 0.7849


# --- summarize -----------------------------------------------------------


def test_summarize_excludes_null_from_means(monkeypatch) -> None:
    # Build a fake dataset with two Category-A queries and one Category-C.
    monkeypatch.setattr(
        "tests.golden.load_dataset",
        lambda: [
            _query("q_a1", "A", must_include="x"),
            _query("q_a2", "A", must_include="y"),
            _query("q_c1", "C", must_include=None),
        ],
    )
    per_query = {
        "q_a1": {"coverage_score": 0.8, "recall_at_k": 1.0, "mrr": 1.0},
        "q_a2": {"coverage_score": 0.6, "recall_at_k": 0.0, "mrr": 0.0},
        "q_c1": {"coverage_score": 0.0, "recall_at_k": None, "mrr": None},
    }
    agg = summarize(per_query)

    # Category A: both A queries contribute.
    assert agg["by_category"]["A"]["coverage_score"] == pytest.approx(0.7)
    assert agg["by_category"]["A"]["recall_at_k"] == pytest.approx(0.5)
    assert agg["by_category"]["A"]["mrr"] == pytest.approx(0.5)

    # Category C: only the C query; recall/MRR are None across the board.
    assert agg["by_category"]["C"]["coverage_score"] == pytest.approx(0.0)
    assert agg["by_category"]["C"]["recall_at_k"] is None
    assert agg["by_category"]["C"]["mrr"] is None

    # Overall: coverage averages across all three; recall/MRR average over A only.
    assert agg["overall"]["coverage_score"] == pytest.approx((0.8 + 0.6 + 0.0) / 3)
    assert agg["overall"]["recall_at_k"] == pytest.approx(0.5)
    assert agg["overall"]["mrr"] == pytest.approx(0.5)


def test_summarize_empty_returns_empty_aggregates(monkeypatch) -> None:
    monkeypatch.setattr("tests.golden.load_dataset", lambda: [])
    agg = summarize({})
    assert agg == {"by_category": {}, "overall": {"coverage_score": None, "recall_at_k": None, "mrr": None}}


# --- compare_to_baseline ------------------------------------------------


def test_compare_to_baseline_no_regression() -> None:
    baseline = {
        "per_query": {"q1": {"coverage_score": 0.7, "recall_at_k": 1.0, "mrr": 0.5}},
        "by_category": {"A": {"coverage_score": 0.7, "recall_at_k": 1.0, "mrr": 0.5}},
        "overall": {"coverage_score": 0.7, "recall_at_k": 1.0, "mrr": 0.5},
    }
    live = baseline  # identical
    assert compare_to_baseline(live, baseline) == []


def test_compare_to_baseline_within_tolerance_is_clean() -> None:
    baseline = {
        "per_query": {"q1": {"coverage_score": 0.70, "recall_at_k": 1.0, "mrr": 0.5}},
        "by_category": {"A": {"coverage_score": 0.70, "recall_at_k": 1.0, "mrr": 0.5}},
        "overall": {"coverage_score": 0.70, "recall_at_k": 1.0, "mrr": 0.5},
    }
    live = {
        "per_query": {"q1": {"coverage_score": 0.695, "recall_at_k": 1.0, "mrr": 0.5}},
        "by_category": {"A": {"coverage_score": 0.695, "recall_at_k": 1.0, "mrr": 0.5}},
        "overall": {"coverage_score": 0.695, "recall_at_k": 1.0, "mrr": 0.5},
    }
    # 0.005 drop, tolerance is 0.01 → clean.
    assert compare_to_baseline(live, baseline) == []


def test_compare_to_baseline_flags_per_query_regression() -> None:
    baseline = {
        "per_query": {"q1": {"coverage_score": 0.70, "recall_at_k": 1.0, "mrr": 0.5}},
        "by_category": {},
        "overall": {"coverage_score": 0.70, "recall_at_k": 1.0, "mrr": 0.5},
    }
    live = {
        "per_query": {"q1": {"coverage_score": 0.60, "recall_at_k": 1.0, "mrr": 0.5}},
        "by_category": {},
        "overall": {"coverage_score": 0.60, "recall_at_k": 1.0, "mrr": 0.5},
    }
    failures = compare_to_baseline(live, baseline)
    assert failures, "0.10 drop must trip"
    assert any("q1" in f and "coverage_score" in f for f in failures)


def test_compare_to_baseline_improvements_not_flagged() -> None:
    baseline = {
        "per_query": {"q1": {"coverage_score": 0.30, "recall_at_k": 0.0, "mrr": 0.0}},
        "by_category": {},
        "overall": {"coverage_score": 0.30, "recall_at_k": 0.0, "mrr": 0.0},
    }
    live = {
        "per_query": {"q1": {"coverage_score": 0.90, "recall_at_k": 1.0, "mrr": 1.0}},
        "by_category": {},
        "overall": {"coverage_score": 0.90, "recall_at_k": 1.0, "mrr": 1.0},
    }
    # All metrics improved — no failures.
    assert compare_to_baseline(live, baseline) == []


def test_compare_to_baseline_ignores_null_baselines() -> None:
    baseline = {
        "per_query": {"q_c": {"coverage_score": 0.0, "recall_at_k": None, "mrr": None}},
        "by_category": {},
        "overall": {"coverage_score": 0.0, "recall_at_k": None, "mrr": None},
    }
    live = {
        "per_query": {"q_c": {"coverage_score": 0.0, "recall_at_k": 0.0, "mrr": 0.0}},
        "by_category": {},
        "overall": {"coverage_score": 0.0, "recall_at_k": 0.0, "mrr": 0.0},
    }
    # When the baseline has None, no comparison happens for that metric.
    assert compare_to_baseline(live, baseline) == []


def test_tolerance_constant_is_one_percent() -> None:
    assert BASELINE_TOLERANCE == 0.01
