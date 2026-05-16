# Tasks — phase-0-project-skeleton

Implements Phase 0 of `docs/COMPENDIUM_BUILD.md`. Some scaffolding (git repo, `.gitignore`, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `README.md`) may already exist from the project bootstrap; the Phase Plan reconciles what is done.

## 1. Project scaffolding

- [ ] 1.1 Ensure `git` is initialized with a `.gitignore` (Python, `.env`, `.venv`, caches; tool dirs excluded)
- [ ] 1.2 `uv init`; set `pyproject.toml` metadata (name `compendium`, Python `>=3.12`); `.python-version` pinned to `3.12`
- [ ] 1.3 Add runtime dependencies: `psycopg[binary]` (v3), `alembic`, `structlog`, `pyyaml`, `python-dotenv`
- [ ] 1.4 Add dev dependencies: `pytest`
- [ ] 1.5 Create the package layout: `compendium/__init__.py` and sub-packages `ingest/`, `wiki/`, `index/`, `retrieve/`, `graph/`, `trace/`, `tui/`, `db/` (each with `__init__.py`); and top-level `config/`, `migrations/`, `tests/`, `vault/concepts/`, `vault/topics/`, `vault/sources/`
- [ ] 1.6 Verify `uv sync` succeeds from a clean state

## 2. Configuration, entrypoint, logging

- [ ] 2.1 Write `.env.example` with required vars: `POSTGRES_URL`, `OPENSEARCH_URL`, `QDRANT_URL`, `MEMGRAPH_URL`, `OPENROUTER_API_KEY`, `EMBED_MODEL`, `VAULT_PATH`
- [ ] 2.2 Write `config/settings.yaml` with non-secret behavior config (chunk sizes, retrieval thresholds, loop intervals) and env-var references by name
- [ ] 2.3 Implement the config loader: load `settings.yaml`, resolve env-var references, validate that every required value is present and parseable, return a validated config object exposing resolved storage URLs and settings; raise a clear error naming any missing variable; perform no network I/O
- [ ] 2.4 Configure `structlog` to emit single-line JSON to stderr
- [ ] 2.5 Implement `compendium/__main__.py`: load and validate config, log `Compendium starting` plus the resolved storage URLs, exit 0; on validation failure print the error and exit non-zero

## 3. Dev environment, docs, verification

- [ ] 3.1 Write `docker-compose.yml` with a single dev-only `postgres:16` service (named volume, port 5432, env-driven db/user/password)
- [ ] 3.2 Write `README.md`: setup steps and the doc reading order
- [ ] 3.3 Add `tests/test_config.py`: config validates with all vars set; fails naming the missing var when one is unset; validation succeeds with backends unreachable
- [ ] 3.4 **Acceptance:** `uv run python -m compendium` starts, validates config, prints `Compendium starting` and the resolved storage URLs, exits 0; `uv run pytest tests/test_config.py` passes
