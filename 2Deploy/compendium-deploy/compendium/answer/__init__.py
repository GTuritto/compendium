"""Composed answers over the page-first wiki (``ask``, v0.2 Phase 6)."""

from __future__ import annotations

from compendium.answer.compose import AskResult, Citation, ask, compose_answer
from compendium.answer.llm import Answerer, Completion, get_answerer

__all__ = [
    "AskResult", "Citation", "ask", "compose_answer",
    "Answerer", "Completion", "get_answerer",
]
