"""Configuration loading and validation.

Reads non-secret behavior config from ``config/settings.yaml`` and resolves
``${VAR}`` references against the environment (and ``.env``, via
python-dotenv). Validation confirms that required values are present and
parseable; it never opens a network connection.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SETTINGS_PATH = _REPO_ROOT / "config" / "settings.yaml"

# Matches ${VAR} and ${VAR:-default}.
_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Resolved, validated configuration."""

    postgres_url: str
    opensearch_url: str
    qdrant_url: str
    memgraph_url: str
    vault_path: str
    synthesis_endpoint: str
    synthesis_model: str
    synthesis_api_key: str
    embeddings_endpoint: str
    embeddings_model: str
    settings: dict[str, Any] = field(default_factory=dict)

    def storage_urls(self) -> dict[str, str]:
        """The four resolved storage URLs, for startup reporting."""
        return {
            "postgres_url": self.postgres_url,
            "opensearch_url": self.opensearch_url,
            "qdrant_url": self.qdrant_url,
            "memgraph_url": self.memgraph_url,
        }


def _resolve(value: Any, missing: list[str]) -> Any:
    """Recursively resolve ${VAR} references in a parsed YAML structure."""
    if isinstance(value, dict):
        return {k: _resolve(v, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, missing) for v in value]
    if isinstance(value, str):
        return _resolve_str(value, missing)
    return value


def _resolve_str(text: str, missing: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        missing.append(name)
        return ""

    return _VAR_PATTERN.sub(replace, text)


def _build(resolved: dict[str, Any]) -> Config:
    storage = resolved["storage"]
    synthesis = resolved["synthesis"]
    embeddings = resolved["embeddings"]
    return Config(
        postgres_url=storage["postgres_url"],
        opensearch_url=storage["opensearch_url"],
        qdrant_url=storage["qdrant_url"],
        memgraph_url=storage["memgraph_url"],
        vault_path=resolved["vault"]["path"],
        synthesis_endpoint=synthesis["endpoint"],
        synthesis_model=synthesis["model"],
        synthesis_api_key=synthesis.get("api_key", ""),
        embeddings_endpoint=embeddings["endpoint"],
        embeddings_model=embeddings["model"],
        settings={
            k: resolved[k] for k in ("ingestion", "retrieval", "loops") if k in resolved
        },
    )


def load_config(
    settings_path: Path | str | None = None,
    *,
    env_file: Path | str | None = None,
    load_env: bool = True,
) -> Config:
    """Load, resolve, and validate configuration.

    Args:
        settings_path: path to settings.yaml; defaults to config/settings.yaml.
        env_file: path to a .env file; defaults to the repo-root .env.
        load_env: when False, skip reading any .env file (used by tests so the
            environment is controlled entirely by the caller).

    Raises:
        ConfigError: if the settings file is missing or invalid YAML, a
            required environment variable is unset, or a required settings key
            is absent.
    """
    if load_env:
        load_dotenv(Path(env_file) if env_file else _REPO_ROOT / ".env")

    path = Path(settings_path) if settings_path else _DEFAULT_SETTINGS_PATH
    if not path.is_file():
        raise ConfigError(f"settings file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"settings file is not valid YAML: {exc}") from exc

    missing: list[str] = []
    resolved = _resolve(raw, missing)
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ConfigError(f"required environment variable(s) not set: {names}")

    try:
        return _build(resolved)
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"settings file is missing a required key: {exc}") from exc
