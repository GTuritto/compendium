"""The embedding seam.

Dense retrieval (Qdrant) needs vectors. Embedding is an injectable seam,
mirroring the Phase 3 ``Synthesizer``: the real adapter calls the pinned
``EMBED_MODEL`` at the configured OpenAI-compatible endpoint; a deterministic
stub produces fixed-dimension vectors offline for tests and the index
integration suite. The Phase 10 eval cached/replay embedder slots in here too.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Protocol


# BGE-M3 dimension; the Qdrant collections are created at this size.
EMBED_DIM = 1024


class Embedder(Protocol):
    """Embeds a batch of texts into fixed-dimension vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class StubEmbedder:
    """A deterministic, offline embedder for tests and verification.

    Each text maps to a stable unit vector seeded by its hash. The vectors are
    not semantic, but they are deterministic and distinct, which is what index
    and rebuild tests need.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        vec = [rng.gauss(0.0, 1.0) for _ in range(EMBED_DIM)]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class OpenAIEmbedder:
    """The real embedder: an OpenAI-compatible embeddings endpoint."""

    def __init__(self, endpoint: str, model: str, api_key: str = "") -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=endpoint, api_key=api_key or "not-needed")
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        from compendium.profiling import timed

        with timed("embedder.embed", model=self._model, batch=len(texts)):
            response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


def get_embedder() -> Embedder:
    """The stub when COMPENDIUM_EMBED_STUB / COMPENDIUM_LLM_STUB is set, else the real endpoint."""
    from compendium.model_clients import get_model_client

    return get_model_client("embedder")
