"""Page coverage scoring (ADR-003 step 5).

RRF fused scores are unbounded sums, not comparable to the configured
``page_coverage_threshold`` of 0.5. The coverage score min-max normalizes the
fused page scores into 0-1 and takes the mean of the top-``top_k`` normalized
scores. Bounded, threshold-comparable, and rewards a cluster of strong pages
over a single lucky hit. Pure: no I/O.

Degenerate cases:
- no pages -> 0.0 (triggers fallback)
- a single page -> 1.0 (one strong page is real coverage)
- all-equal scores -> 1.0 (every page normalizes to the max)
"""

from __future__ import annotations


def coverage_score(fused_scores: list[float], top_k: int) -> float:
    """The mean of the top-``top_k`` min-max-normalized fused scores.

    Args:
        fused_scores: fused page scores in any order (descending is typical).
        top_k: the coverage window (config ``retrieval.top_k``, default 7).

    Returns:
        A value in 0.0-1.0. Empty input returns 0.0.
    """
    if not fused_scores or top_k <= 0:
        return 0.0

    lo, hi = min(fused_scores), max(fused_scores)
    if hi == lo:
        # All scores equal (includes the single-page case): full normalized.
        normalized = [1.0] * len(fused_scores)
    else:
        span = hi - lo
        normalized = [(s - lo) / span for s in fused_scores]

    top = sorted(normalized, reverse=True)[:top_k]
    return sum(top) / len(top)
