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
