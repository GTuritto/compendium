"""The model-client selection registry (arch-llm-client-seam).

Unit tests; no network. Confirms per-role stub/real selection, the umbrella
offline switch, and that the four named factories delegate to the registry.
The real-client branch is exercised by type only (constructed from config, no
call), under the per-role flag being unset.
"""

from __future__ import annotations

import pytest

from compendium import model_clients as mc

_REQUIRED = {
    "POSTGRES_URL": "postgresql://compendium:compendium@localhost:5432/compendium",
    "OPENSEARCH_URL": "http://localhost:9200",
    "QDRANT_URL": "http://localhost:6533",
    "MEMGRAPH_URL": "bolt://localhost:7688",
    "VAULT_PATH": "./vault",
    "SYNTHESIS_ENDPOINT": "https://openrouter.ai/api/v1",
    "SYNTHESIS_MODEL": "anthropic/claude-sonnet-4.5",
    "EMBEDDINGS_ENDPOINT": "http://localhost:12434/engines/v1",
    "EMBED_MODEL": "BAAI/bge-m3",
}

_ROLES = ("answerer", "synthesizer", "extractor", "embedder")


@pytest.fixture
def env(monkeypatch):
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)
    for flag in ("COMPENDIUM_LLM_STUB", "COMPENDIUM_SYNTH_STUB", "COMPENDIUM_EMBED_STUB"):
        monkeypatch.delenv(flag, raising=False)
    return monkeypatch


def test_registry_has_the_four_roles():
    assert set(mc.REGISTRY) == set(_ROLES)
    assert mc.REGISTRY["embedder"].stub_env == "COMPENDIUM_EMBED_STUB"
    assert mc.REGISTRY["answerer"].stub_env == "COMPENDIUM_SYNTH_STUB"


def test_each_role_returns_its_real_client_by_default(env):
    from compendium.answer.llm import LLMAnswerer
    from compendium.wiki.synth import LLMSynthesizer
    from compendium.curate.extract import LLMExtractor
    from compendium.index.embedder import OpenAIEmbedder

    assert isinstance(mc.get_model_client("answerer"), LLMAnswerer)
    assert isinstance(mc.get_model_client("synthesizer"), LLMSynthesizer)
    assert isinstance(mc.get_model_client("extractor"), LLMExtractor)
    assert isinstance(mc.get_model_client("embedder"), OpenAIEmbedder)


def test_per_role_flag_forces_only_its_role(env):
    from compendium.index.embedder import StubEmbedder, OpenAIEmbedder
    from compendium.wiki.synth import LLMSynthesizer

    env.setenv("COMPENDIUM_EMBED_STUB", "1")
    assert isinstance(mc.get_model_client("embedder"), StubEmbedder)
    # synthesizer (a SYNTH-flag role) is unaffected by the EMBED flag
    assert isinstance(mc.get_model_client("synthesizer"), LLMSynthesizer)


def test_synth_flag_stubs_the_three_synth_roles_not_the_embedder(env):
    from compendium.answer.llm import StubAnswerer
    from compendium.wiki.synth import StubSynthesizer
    from compendium.curate.extract import StubExtractor
    from compendium.index.embedder import OpenAIEmbedder

    env.setenv("COMPENDIUM_SYNTH_STUB", "1")
    assert isinstance(mc.get_model_client("answerer"), StubAnswerer)
    assert isinstance(mc.get_model_client("synthesizer"), StubSynthesizer)
    assert isinstance(mc.get_model_client("extractor"), StubExtractor)
    assert isinstance(mc.get_model_client("embedder"), OpenAIEmbedder)  # embedder real


def test_umbrella_flag_stubs_every_role(env):
    from compendium.answer.llm import StubAnswerer
    from compendium.wiki.synth import StubSynthesizer
    from compendium.curate.extract import StubExtractor
    from compendium.index.embedder import StubEmbedder

    env.setenv("COMPENDIUM_LLM_STUB", "1")
    assert isinstance(mc.get_model_client("answerer"), StubAnswerer)
    assert isinstance(mc.get_model_client("synthesizer"), StubSynthesizer)
    assert isinstance(mc.get_model_client("extractor"), StubExtractor)
    assert isinstance(mc.get_model_client("embedder"), StubEmbedder)


def test_unknown_role_raises(env):
    with pytest.raises(KeyError):
        mc.get_model_client("reranker")
