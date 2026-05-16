"""Tests for configuration loading and validation."""

import pytest

from compendium.config import Config, ConfigError, load_config

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
    """Set every required variable; leave the optional API key unset."""
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return monkeypatch


def test_loads_with_all_vars_set(env):
    config = load_config(load_env=False)
    assert isinstance(config, Config)
    assert config.storage_urls() == {
        "postgres_url": _REQUIRED["POSTGRES_URL"],
        "opensearch_url": _REQUIRED["OPENSEARCH_URL"],
        "qdrant_url": _REQUIRED["QDRANT_URL"],
        "memgraph_url": _REQUIRED["MEMGRAPH_URL"],
    }
    assert config.synthesis_model == _REQUIRED["SYNTHESIS_MODEL"]
    assert config.synthesis_api_key == ""  # optional, defaulted when unset
    assert "retrieval" in config.settings


def test_missing_required_var_raises_naming_it(env):
    env.delenv("QDRANT_URL")
    with pytest.raises(ConfigError, match="QDRANT_URL"):
        load_config(load_env=False)


def test_validation_does_no_io(env):
    # Point the backends at an unroutable address. Validation must still
    # succeed: it only resolves and parses values, it never connects.
    for key in ("POSTGRES_URL", "OPENSEARCH_URL", "QDRANT_URL", "MEMGRAPH_URL"):
        env.setenv(key, "http://203.0.113.1:1")
    config = load_config(load_env=False)
    assert config.qdrant_url == "http://203.0.113.1:1"
