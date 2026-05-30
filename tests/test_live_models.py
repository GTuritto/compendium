"""Live-model validation tests (v0.2 Phase 1).

Opt-in via ``uv run pytest -m live``. Excluded by default through ``addopts``
in ``pyproject.toml``. Each test skips (does not fail) when the corresponding
stub env var is set or the configured endpoint is unreachable, so a laptop
without DMR or OpenRouter access does not produce a red suite.

Cost: the synthesis test makes one real LLM call per invocation; the embedder
test makes one embeddings call. Both run only when the curator opts in.
"""

from __future__ import annotations

import math
import os

import httpx
import pytest

from compendium.config import load_config
from compendium.index.embedder import EMBED_DIM, get_embedder
from compendium.wiki.synth import get_synthesizer

_PROBE_TIMEOUT_S = 2.0


def _endpoint_reachable(url: str) -> bool:
    """A short GET probe. Any HTTP response (even 4xx/5xx) means reachable."""
    try:
        httpx.get(url, timeout=_PROBE_TIMEOUT_S)
        return True
    except httpx.HTTPError:
        return False


@pytest.mark.live
def test_real_embedder_roundtrip() -> None:
    if os.environ.get("COMPENDIUM_EMBED_STUB"):
        pytest.skip("COMPENDIUM_EMBED_STUB set; live embedder test skipped")
    config = load_config()
    if not _endpoint_reachable(config.embeddings_endpoint):
        pytest.skip(f"embeddings endpoint unreachable: {config.embeddings_endpoint}")

    embedder = get_embedder()
    texts = [
        "Compendium is a personal knowledge synthesis system.",
        "Pages are the unit of retrieval, not chunks.",
        "The wiki is canonical; derived indexes rebuild from PostgreSQL and the vault.",
    ]
    vectors = embedder.embed(texts)

    assert len(vectors) == len(texts), (
        f"expected {len(texts)} vectors, got {len(vectors)}"
    )
    for i, v in enumerate(vectors):
        assert len(v) == EMBED_DIM, (
            f"vector {i}: expected {EMBED_DIM} dims, got {len(v)}"
        )
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-3, (
            f"vector {i}: norm {norm} not unit-normalized within 1e-3"
        )
    assert vectors[0] != vectors[1], "vectors 0 and 1 should be distinct"
    assert vectors[1] != vectors[2], "vectors 1 and 2 should be distinct"
    assert vectors[0] != vectors[2], "vectors 0 and 2 should be distinct"


@pytest.mark.live
def test_real_synthesizer_writes_prose() -> None:
    if os.environ.get("COMPENDIUM_SYNTH_STUB"):
        pytest.skip("COMPENDIUM_SYNTH_STUB set; live synthesizer test skipped")
    config = load_config()
    if not _endpoint_reachable(config.synthesis_endpoint):
        pytest.skip(f"synthesis endpoint unreachable: {config.synthesis_endpoint}")

    synthesizer = get_synthesizer()
    chunks = [
        {
            "source_title": "Compendium Design",
            "body": (
                "Compendium is a personal knowledge synthesis system. It ingests "
                "sources, synthesizes a canonical Markdown wiki, and answers "
                "queries by retrieving from that wiki rather than raw chunks."
            ),
        },
        {
            "source_title": "Architecture Note",
            "body": (
                "The Markdown wiki is canonical: OpenSearch, Qdrant, and Memgraph "
                "are derived indexes rebuilt from PostgreSQL and the vault."
            ),
        },
    ]
    body = synthesizer.synthesize("Compendium", chunks)

    assert body.startswith("# "), f"body does not start with H1: {body[:80]!r}"
    assert len(body) >= 200, f"body shorter than 200 chars: {len(body)}"
    assert "stub synthesizer" not in body, "body contains the stub-only phrase"
