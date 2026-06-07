"""The cached config accessor + per-section readers (arch-config-cache-seam).

Unit tests; no stores. The behavior-config parse is cached and invalidatable;
``load_config(...)`` stays the uncached primitive. The section readers resolve the
same values the former inline extractors did.
"""

from __future__ import annotations

import pytest

import compendium.config as cfg

_REQUIRED = {
    "POSTGRES_URL": "postgresql://compendium:compendium@localhost:5432/compendium",
    "OPENSEARCH_URL": "http://localhost:9200",
    "QDRANT_URL": "http://localhost:6333",
    "MEMGRAPH_URL": "bolt://localhost:7687",
    "VAULT_PATH": "./vault",
    "SYNTHESIS_ENDPOINT": "https://openrouter.ai/api/v1",
    "SYNTHESIS_MODEL": "anthropic/claude-sonnet-4.5",
    "EMBEDDINGS_ENDPOINT": "http://localhost:12434/engines/v1",
    "EMBED_MODEL": "BAAI/bge-m3",
}


@pytest.fixture
def env(monkeypatch):
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg.invalidate_config_cache()
    yield monkeypatch
    cfg.invalidate_config_cache()


def test_get_config_parses_once(env, monkeypatch):
    calls = {"n": 0}
    real = cfg.load_config

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(cfg, "load_config", counting)
    first = cfg.get_config()
    second = cfg.get_config()
    assert first is second
    assert calls["n"] == 1  # parsed once, then served from cache


def test_invalidate_forces_a_reread(env, monkeypatch):
    calls = {"n": 0}
    real = cfg.load_config

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(cfg, "load_config", counting)
    cfg.get_config()
    cfg.invalidate_config_cache()
    cfg.get_config()
    assert calls["n"] == 2


def test_load_config_is_uncached(env):
    cfg.invalidate_config_cache()
    cfg.load_config(load_env=False)  # the primitive must not populate the cache
    assert cfg._cached is None


# --- section readers --------------------------------------------------------


def test_section_readers_expose_the_right_keys(env):
    from compendium import config_sections as cs

    assert set(cs.retrieval()) == {"rrf_k", "page_coverage_threshold", "top_k"}
    assert set(cs.expansion()) == {"enabled", "seed_k", "max_hops", "decay", "weight"}
    assert set(cs.ask()) == {"refuse_below_coverage", "prompt_template_id", "rewrite", "top_k"}
    assert cs.ask()["top_k"] == cs.retrieval()["top_k"]  # cross-read via retrieval()
    assert set(cs.curation()) == {"thin_grounding_min", "low_coverage_threshold"}
    assert set(cs.extract()) == {"enabled", "min_confidence", "top_k_neighbours", "full_sweep_every"}
    ingestion = cs.ingestion()
    assert set(ingestion) == {"max_source_bytes", "min_text_tokens", "target_tokens", "overlap_tokens"}
    assert "vault_path" not in ingestion  # env-sensitive; read via load_config() in ingest


def test_section_readers_fall_back_to_documented_defaults(monkeypatch, tmp_path):
    # A settings.yaml with only the required storage/synth/embeddings blocks: the
    # behavior readers must still return their defaults (parity with the old
    # inline extractors).
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "storage:\n"
        "  postgres_url: ${POSTGRES_URL}\n"
        "  opensearch_url: ${OPENSEARCH_URL}\n"
        "  qdrant_url: ${QDRANT_URL}\n"
        "  memgraph_url: ${MEMGRAPH_URL}\n"
        "vault:\n  path: ${VAULT_PATH}\n"
        "synthesis:\n  endpoint: ${SYNTHESIS_ENDPOINT}\n  model: ${SYNTHESIS_MODEL}\n"
        "embeddings:\n  endpoint: ${EMBEDDINGS_ENDPOINT}\n  model: ${EMBED_MODEL}\n"
    )
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)
    from compendium import config_sections as cs

    monkeypatch.setattr(
        cfg, "get_config", lambda: cfg.load_config(settings_path=settings, load_env=False)
    )
    assert cs.retrieval() == {"rrf_k": 60, "page_coverage_threshold": 0.5, "top_k": 7}
    assert cs.expansion()["seed_k"] == 3
    assert cs.ask()["refuse_below_coverage"] == 0.3 and cs.ask()["rewrite"] is True
    assert cs.curation() == {"thin_grounding_min": 2, "low_coverage_threshold": 0.5}
    assert cs.extract() == {
        "enabled": True, "min_confidence": 0.7, "top_k_neighbours": 10, "full_sweep_every": 24,
    }
    assert cs.ingestion() == {
        "max_source_bytes": 200 * 1024 * 1024, "min_text_tokens": 1000,
        "target_tokens": 512, "overlap_tokens": 64,
    }
