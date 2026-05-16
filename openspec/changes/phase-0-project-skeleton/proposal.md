## Why

Compendium is fully designed (`docs/Compendium.md`) but has no runnable code. Phase 0 of the build plan delivers the project skeleton: a `uv`-managed Python project that starts, loads and validates its configuration, reports its resolved storage URLs, and exits cleanly. Every later phase builds on this skeleton, and no phase can be tested until it exists.

## What Changes

- New `uv`-managed Python 3.12 project: `pyproject.toml`, `.python-version`, dependency set.
- Package layout: `compendium/{ingest,wiki,index,retrieve,graph,trace,tui,db}/`, plus `config/`, `migrations/`, `tests/`, `vault/`.
- Configuration system: `.env.example` (secret/URL vars), `config/settings.yaml` (non-secret behavior config), and a loader that resolves env-var references at startup and validates them. Validation is parse/resolve only — no connection attempts.
- `python -m compendium` entrypoint that loads and validates config, prints "Compendium starting" and the resolved storage URLs, and exits cleanly.
- Structured logging: `structlog` emitting JSON to stderr.
- A dev-only single-service `docker-compose.yml` running a pinned `postgres:16` (provisioning for Phase 1 and beyond).
- `README.md` with setup instructions and the doc reading order.
- Repository initialized with `git` and a `.gitignore`.

## Capabilities

### New Capabilities

- `project-skeleton`: A runnable, configured Python project — package layout, dependency management, the `python -m compendium` entrypoint, configuration loading and validation, and structured logging.

### Modified Capabilities

<!-- None — Phase 0 is the first phase; no prior specs exist. -->

## Impact

- New project files: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `.gitignore`, `README.md`, `docker-compose.yml`.
- New code: the `compendium/` package (sub-packages mostly empty placeholders for later phases), `config/settings.yaml` + loader, `tests/test_config.py`.
- New dependencies: `psycopg[binary]` (v3), `alembic`, `structlog`, `pyyaml`, `python-dotenv`, plus `pytest` for tests.
- Establishes foundational technical decisions inherited by all later phases: sync database access, raw SQL over an ORM, and a single-service dev `docker-compose.yml`.
