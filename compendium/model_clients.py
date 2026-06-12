"""One registry for stub-or-real model-client selection (arch-llm-client-seam).

Four model seams share the same selection shape — an env-flag picks a stub, else
the real client is built from config. This module is the single home for that
decision: ``get_model_client(role)`` reads the role's flag (or the umbrella
``COMPENDIUM_LLM_STUB``) and returns the stub or the real client. The four named
factories (``get_answerer`` / ``get_synthesizer`` / ``get_extractor`` /
``get_embedder``) delegate here; the protocols and stub implementations are
unchanged and stay in their own modules.

The builders are **lazy thunks** — each imports its client classes and reads
config inside the function body — so this module imports none of the four client
modules at load time, and there is no import cycle (the client modules continue
to be imported by ``answer/`` / ``wiki/`` / ``curate/`` / ``index/``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

# Set this to run every model seam offline in one switch. It is additive: the
# per-role flags (COMPENDIUM_SYNTH_STUB / COMPENDIUM_EMBED_STUB) still force their
# own roles independently.
UMBRELLA_STUB_ENV = "COMPENDIUM_LLM_STUB"


@dataclass(frozen=True)
class ModelRole:
    """One model seam: its own stub env-flag and lazy stub/real builders."""

    stub_env: str
    make_stub: Callable[[], Any]
    make_real: Callable[[], Any]


# --- lazy builders (imports inside, so no import cycle at module load) -------


def _answerer_stub() -> Any:
    from compendium.answer.llm import StubAnswerer

    return StubAnswerer()


def _answerer_real() -> Any:
    from compendium.answer.llm import LLMAnswerer
    from compendium.config import load_config

    c = load_config()
    return LLMAnswerer(c.synthesis_endpoint, c.synthesis_model, c.synthesis_api_key)


def _synthesizer_stub() -> Any:
    from compendium.wiki.synth import StubSynthesizer

    return StubSynthesizer()


def _synthesizer_real() -> Any:
    from compendium.config import load_config
    from compendium.wiki.synth import LLMSynthesizer

    c = load_config()
    return LLMSynthesizer(c.synthesis_endpoint, c.synthesis_model, c.synthesis_api_key)


def _extractor_stub() -> Any:
    from compendium.curate.extract import StubExtractor

    return StubExtractor()


def _extractor_real() -> Any:
    from compendium.config import load_config
    from compendium.curate.extract import LLMExtractor

    c = load_config()
    return LLMExtractor(c.synthesis_endpoint, c.synthesis_model, c.synthesis_api_key)


def _contradictor_stub() -> Any:
    from compendium.curate.contradict import StubContradictor

    return StubContradictor()


def _contradictor_real() -> Any:
    from compendium.config import load_config
    from compendium.curate.contradict import LLMContradictor

    c = load_config()
    return LLMContradictor(c.synthesis_endpoint, c.synthesis_model, c.synthesis_api_key)


def _embedder_stub() -> Any:
    from compendium.index.embedder import StubEmbedder

    return StubEmbedder()


def _embedder_real() -> Any:
    from compendium.config import load_config
    from compendium.index.embedder import OpenAIEmbedder

    c = load_config()
    return OpenAIEmbedder(c.embeddings_endpoint, c.embeddings_model, c.embeddings_api_key)


REGISTRY: dict[str, ModelRole] = {
    "answerer": ModelRole("COMPENDIUM_SYNTH_STUB", _answerer_stub, _answerer_real),
    "synthesizer": ModelRole("COMPENDIUM_SYNTH_STUB", _synthesizer_stub, _synthesizer_real),
    "extractor": ModelRole("COMPENDIUM_SYNTH_STUB", _extractor_stub, _extractor_real),
    "contradictor": ModelRole("COMPENDIUM_SYNTH_STUB", _contradictor_stub, _contradictor_real),
    "embedder": ModelRole("COMPENDIUM_EMBED_STUB", _embedder_stub, _embedder_real),
}


def use_stub(role: str) -> bool:
    """True when ``role`` should be stubbed — the umbrella flag or its own flag."""
    r = REGISTRY[role]
    return bool(os.environ.get(UMBRELLA_STUB_ENV) or os.environ.get(r.stub_env))


def get_model_client(role: str) -> Any:
    """The stub or real client for ``role`` (one of the REGISTRY keys).

    Returns the stub when ``COMPENDIUM_LLM_STUB`` or the role's own flag is set,
    else the real client built from config. Raises ``KeyError`` for an unknown role.
    """
    r = REGISTRY[role]
    return r.make_stub() if use_stub(role) else r.make_real()


# --- the chat-completion envelope (arch-chat-envelope) ----------------------
#
# What every *real* chat-role client shares once the registry has selected it:
# one construction site for the OpenAI-compatible client and one mechanical
# call envelope with uniform token accounting. Prompt assembly and result
# shaping stay in each client class; stubs never cross this seam.


@dataclass(frozen=True)
class Completion:
    """One LLM call's text plus its token accounting."""

    text: str
    input_tokens: int
    output_tokens: int


def _approx_tokens(text: str) -> int:
    """A tokenizer-free heuristic used when the response carries no usage."""
    return max(1, len(text) // 4) if text else 0


def make_openai_client(endpoint: str, api_key: str) -> Any:
    """The one place an OpenAI-compatible chat client is constructed."""
    from openai import OpenAI

    return OpenAI(base_url=endpoint, api_key=api_key or "not-needed")


def chat(
    client: Any,
    model: str,
    system: str,
    user: str,
    *,
    on_token: Callable[[str], None] | None = None,
) -> Completion:
    """One chat completion over a ``[system, user]`` prompt.

    Buffers when ``on_token`` is None; streams otherwise, forwarding each
    delta and capturing the usage block from the final chunk
    (``include_usage``). Token counts come from the response's usage block
    when present, else the char/4 heuristic over the user message (input)
    and the returned text (output).
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if on_token is None:
        response = client.chat.completions.create(model=model, messages=messages)
        text = response.choices[0].message.content or ""
        usage = response.usage
        return Completion(
            text,
            usage.prompt_tokens if usage else _approx_tokens(user),
            usage.completion_tokens if usage else _approx_tokens(text),
        )

    stream = client.chat.completions.create(
        model=model,
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
        usage.prompt_tokens if usage else _approx_tokens(user),
        usage.completion_tokens if usage else _approx_tokens(text),
    )
