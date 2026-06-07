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
