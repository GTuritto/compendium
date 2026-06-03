"""The LLM query-rewrite step for ``ask`` (Shape D part 2, v0.2 Phase 6).

The rewrite runs only inside the ``ask`` flow; the cost-free ``query`` hot path
keeps the Phase 5 rule-based normalization as its only transformation. When
disabled, this is a passthrough that makes no LLM call (zero tokens).
"""

from __future__ import annotations

from compendium.answer.llm import Answerer, Completion


def rewrite_query(
    question: str, answerer: Answerer, *, enabled: bool = True
) -> Completion:
    """Rewrite the question into a retrieval query, or pass it through.

    The rewritten text drives ``pipeline.query``; the original question drives
    composition. When ``enabled`` is false, returns the question unchanged with
    zero token cost and makes no call.
    """
    if not enabled:
        return Completion(question, 0, 0)
    return answerer.rewrite(question)
