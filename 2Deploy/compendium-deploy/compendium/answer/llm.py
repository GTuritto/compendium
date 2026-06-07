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
from dataclasses import dataclass
from typing import Protocol

from compendium.answer.prompts import (
    COMPOSE_SYSTEM,
    REWRITE_SYSTEM,
    compose_user,
    rewrite_user,
)


@dataclass
class Completion:
    """One LLM call's text plus its token accounting."""

    text: str
    input_tokens: int
    output_tokens: int


def _approx_tokens(text: str) -> int:
    """A tokenizer-free heuristic used when the response carries no usage."""
    return max(1, len(text) // 4) if text else 0


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
    """The real answerer: OpenAI-compatible chat completions."""

    def __init__(self, endpoint: str, model: str, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=endpoint, api_key=api_key or "not-needed")
        self.model = model
        self.endpoint = endpoint

    def rewrite(self, question: str) -> Completion:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user", "content": rewrite_user(question)},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        usage = response.usage
        return Completion(
            text or question,
            usage.prompt_tokens if usage else _approx_tokens(question),
            usage.completion_tokens if usage else _approx_tokens(text),
        )

    def compose(
        self,
        question: str,
        context: str,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> Completion:
        messages = [
            {"role": "system", "content": COMPOSE_SYSTEM},
            {"role": "user", "content": compose_user(question, context)},
        ]
        if on_token is None:
            response = self._client.chat.completions.create(
                model=self.model, messages=messages
            )
            text = response.choices[0].message.content or ""
            usage = response.usage
            return Completion(
                text,
                usage.prompt_tokens if usage else _approx_tokens(question + context),
                usage.completion_tokens if usage else _approx_tokens(text),
            )

        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        parts: list[str] = []
        usage = None
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    parts.append(delta)
                    on_token(delta)
            if getattr(chunk, "usage", None):
                usage = chunk.usage
        text = "".join(parts)
        return Completion(
            text,
            usage.prompt_tokens if usage else _approx_tokens(question + context),
            usage.completion_tokens if usage else _approx_tokens(text),
        )


def get_answerer() -> Answerer:
    """The stub when COMPENDIUM_SYNTH_STUB / COMPENDIUM_LLM_STUB is set, else the real client."""
    from compendium.model_clients import get_model_client

    return get_model_client("answerer")
