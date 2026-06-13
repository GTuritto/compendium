"""Page-space scoring for the A/B harness (ADR-016).

Both arms are scored in page space against a probe's ``expected`` page slugs:
the page arm's ranking is its page slugs; the chunk arm's ranking is each
chunk reduced to its parent source page slug (deduplicated, order preserved).
Metrics are hit@k, recall@k, and MRR at ``k`` (default ``retrieval.top_k``).

Pure functions over already-resolved slug lists; no I/O. The chunk→page
resolution (a DB join) happens in ``run.py`` and is passed in here as a list.
"""

from __future__ import annotations

from typing import Any


def _dedupe(slugs: list[str]) -> list[str]:
    """Order-preserving de-duplication (a source page reached by many chunks
    counts once, at its best rank)."""
    seen: set[str] = set()
    out: list[str] = []
    for s in slugs:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def page_slugs_from_pages(result: Any) -> list[str]:
    """The page arm's ranking as page slugs, best first."""
    return _dedupe([p.slug for p in (result.pages or [])])


def score(ranked_slugs: list[str], expected: list[str], k: int) -> dict[str, Any]:
    """hit@k / recall@k / MRR for one ranked slug list against ``expected``.

    ``expected`` is the set of relevant page slugs (curator-labelled at freeze
    time). ``recall@k`` is the fraction of expected slugs present in the top
    ``k``; ``hit@k`` is 1.0 if any expected slug is in the top ``k``; ``MRR``
    uses the rank of the first expected slug.
    """
    ranked = _dedupe(ranked_slugs)
    top = ranked[:k]
    expected_set = set(expected)

    found = [s for s in top if s in expected_set]
    hit_at_k = 1.0 if found else 0.0
    recall_at_k = (
        len(set(top) & expected_set) / len(expected_set) if expected_set else 0.0
    )
    mrr = 0.0
    for rank, slug in enumerate(top, start=1):
        if slug in expected_set:
            mrr = 1.0 / rank
            break

    return {
        "hit_at_k": hit_at_k,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "ranked": ranked,
        "matched": found,
    }


def delta(page_metrics: dict[str, Any], chunk_metrics: dict[str, Any]) -> dict[str, float]:
    """Page-arm-minus-chunk-arm deltas for the three metrics."""
    return {
        key: round(float(page_metrics[key]) - float(chunk_metrics[key]), 6)
        for key in ("hit_at_k", "recall_at_k", "mrr")
    }


def aggregate(per_query: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean page/chunk metrics and mean delta over all probes."""
    n = len(per_query)
    if n == 0:
        return {"n": 0}

    def _mean(arm: str, key: str) -> float:
        return round(sum(float(r[arm][key]) for r in per_query) / n, 6)

    keys = ("hit_at_k", "recall_at_k", "mrr")
    page = {k: _mean("page", k) for k in keys}
    chunk = {k: _mean("chunk", k) for k in keys}
    return {
        "n": n,
        "page": page,
        "chunk": chunk,
        "delta": {k: round(page[k] - chunk[k], 6) for k in keys},
    }
