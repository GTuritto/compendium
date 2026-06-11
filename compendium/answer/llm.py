"""The LLM seam for ``ask`` (v0.2 Phase 6).

A small ``Answerer`` protocol with two calls — ``rewrite`` (Shape D part 2) and
``compose`` — over the same ``SYNTHESIS_*`` config as ``compendium synth``. The
stub is deterministic for the hermetic test tier; the real client is an
OpenAI-compatible chat completion. ``compose`` streams when given an
``on_token`` callback, otherwise it buffers; either way it reports token counts
(from the response usage block when present, else a char/4 heuristic).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

# Completion and the token heuristic live with the chat envelope
# (arch-chat-envelope); re-exported here so existing importers
# (answer/__init__.py, answer/compose.py) are unchanged.
from compendium.model_clients import Completion, _approx_tokens, chat, make_openai_client

from compendium.answer.prompts import (
    COMPOSE_SYSTEM,
    REWRITE_SYSTEM,
    compose_user,
    rewrite_user,
)

__all__ = ["Answerer", "Completion", "LLMAnswerer", "StubAnswerer", "get_answerer"]


class Answerer(Protocol):
    """Rewrites a question and composes an answer over wiki page excerpts."""

    model: str
    endpoint: str

    def rewrite(self, question: str) -> Completion: ...

    def compose(
        self,
        question: str,
        context: str,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> Completion: ...


class StubAnswerer:
    """A deterministic answerer for tests and offline verification."""

    model = "stub"
    endpoint = "stub"

    def rewrite(self, question: str) -> Completion:
        text = question.strip()
        return Completion(text, _approx_tokens(question), _approx_tokens(text))

    def compose(
        self,
        question: str,
        context: str,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> Completion:
        text = (
            "Based on the retrieved wiki pages, here is a grounded answer to "
            f'"{question.strip()}". See the cited pages for detail.'
        )
        if on_token is not None:
            on_token(text)
        return Completion(
            text, _approx_tokens(question + context), _approx_tokens(text)
        )


class LLMAnswerer:
    """The real answerer: prompt assembly + result shaping over the chat envelope."""

    def __init__(self, endpoint: str, model: str, api_key: str) -> None:
        self._client = make_openai_client(endpoint, api_key)
        self.model = model
        self.endpoint = endpoint

    def rewrite(self, question: str) -> Completion:
        completion = chat(self._client, self.model, REWRITE_SYSTEM, rewrite_user(question))
        text = completion.text.strip()
        return Completion(text or question, completion.input_tokens, completion.output_tokens)

    def compose(
        self,
        question: str,
        context: str,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> Completion:
        return chat(
            self._client,
            self.model,
            COMPOSE_SYSTEM,
            compose_user(question, context),
            on_token=on_token,
        )


def get_answerer() -> Answerer:
    """The stub when COMPENDIUM_SYNTH_STUB / COMPENDIUM_LLM_STUB is set, else the real client."""
    from compendium.model_clients import get_model_client

    return get_model_client("answerer")
