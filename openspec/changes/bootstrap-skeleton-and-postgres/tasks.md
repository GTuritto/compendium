# Tasks — bootstrap-skeleton-and-postgres

Implementation is divided into **Phase 0** (project skeleton, groups 1–3) and **Phase 1** (PostgreSQL operational backbone, groups 4–7). Do not begin Phase 1 until Phase 0's verification (task 3.4) passes.

## 1. Phase 0 — Project scaffolding

- [ ] 1.1 Run `git init`; add `.gitignore` (Python, `.env`, `.venv`, `__pycache__`, `uv.lock` kept, vault build artifacts)
- [ ] 1.2 Run `uv init`; set `pyproject.toml` project metadata (name `compendium`, Python `>=3.12`); write `.python-version` pinned to `3.12`
- [ ] 1.3 Add runtime dependencies: `psycopg[binary]` (v3), `alembic`, `structlog`, `pyyaml`, `python-dotenv`
- [ ] 1.4 Add dev dependencies: `pytest`
- [ ] 1.5 Create the package layout: `compendium/__init__.py` and sub-packages `ingest/`, `wiki/`, `index/`, `retrieve/`, `graph/`, `trace/`, `tui/`, `db/` (each with `__init__.py`); and top-level `config/`, `migrations/`, `tests/`, `vault/concepts/`, `vault/topics/`, `vault/sources/`
- [ ] 1.6 Verify `uv sync` succeeds from a clean state

## 2. Phase 0 — Configuration, entrypoint, logging

- [ ] 2.1 Write `.env.example` with required vars: `POSTGRES_URL`, `OPENSEARCH_URL`, `QDRANT_URL`, `MEMGRAPH_URL`, `OPENROUTER_API_KEY`, `EMBED_MODEL`, `VAULT_PATH`
- [ ] 2.2 Write `config/settings.yaml` with non-secret behavior config (chunk sizes, retrieval thresholds, loop intervals) and env-var references by name
- [ ] 2.3 Implement the config loader (`compendium/config.py` or similar): load `settings.yaml`, resolve env-var references, validate that every required value is present and parseable, return a validated config object exposing resolved storage URLs and settings; raise a clear error naming any missing variable; perform no network I/O
- [ ] 2.4 Configure `structlog` to emit single-line JSON to stderr
- [ ] 2.5 Implement `compendium/__main__.py`: load and validate config, log `Compendium starting` plus the resolved storage URLs, exit 0; on validation failure print the error and exit non-zero

## 3. Phase 0 — Dev environment, docs, verification

- [ ] 3.1 Write `docker-compose.yml` with a single dev-only `postgres:16` service (named volume, port 5432, env-driven db/user/password)
- [ ] 3.2 Write `README.md`: setup steps (`git`, `uv sync`, `docker compose up -d`, `.env`, `alembic upgrade head`) and the doc reading order
- [ ] 3.3 Add `tests/test_config.py`: config validates with all vars set; fails naming the missing var when one is unset; validation succeeds with backends unreachable
- [ ] 3.4 **Phase 0 acceptance:** `uv run python -m compendium` starts, validates config, prints `Compendium starting` and the resolved storage URLs, exits 0; `uv run pytest tests/test_config.py` passes

## 4. Phase 1 — Alembic setup

- [ ] 4.1 Run `alembic init migrations`; point `migrations/env.py` at `POSTGRES_URL` from the config loader, using a synchronous engine
- [ ] 4.2 Configure Alembic for hand-written migrations (no autogenerate); set `alembic.ini` script location and naming
- [ ] 4.3 Bring up the dev database (`docker compose up -d`) and confirm `alembic` connects

## 5. Phase 1 — Schema migrations (documented 10-step order)

- [ ] 5.1 Migration 1 — enums: `source_kind`, `page_kind`, `page_status`, `page_generator`, `inspection_status`, `index_kind`, `sync_state`, `promotion_kind`, `curation_signal_kind`, `curation_signal_status`
- [ ] 5.2 Migration 2 — `sources` (incl. `UNIQUE (kind, content_hash)`, title GIN index) and `source_documents`
- [ ] 5.3 Migration 3 — `corpus_revisions`
- [ ] 5.4 Migration 4 — `chunks` (incl. `UNIQUE (source_id, body_hash)`, `chunks_source_pos_idx`)
- [ ] 5.5 Migration 5 — `wiki_pages` (incl. `UNIQUE (kind, slug)`, self-FK `parent_topic_id`) and `wiki_pages_topics` M2M
- [ ] 5.6 Migration 6 — `wiki_page_revisions`, its `(page_id, created_at DESC)` index, then the deferred `wiki_pages.current_revision_id` FK via `ALTER TABLE`
- [ ] 5.7 Migration 7 — `index_sync_state` (incl. unique triple, partial `index_sync_pending_idx`)
- [ ] 5.8 Migration 8 — `promotion_events`
- [ ] 5.9 Migration 9 — `query_traces` with `query_embedding REAL[]` (nullable, no pgvector), `query_traces_corpus_idx`, partial `query_traces_fallback_idx`
- [ ] 5.10 Migration 10 — `graph_curation_signals`, `graph_analysis_runs`, the deferred `run_id` FK, partial `curation_signals_open_idx`
- [ ] 5.11 Ensure every migration has a correct `downgrade` that reverses its `upgrade` (drop in reverse dependency order, including enums and deferred FKs)

## 6. Phase 1 — Operational views and access layer

- [ ] 6.1 Migration 11 — read-only views: `v_sync_lag`, `v_failed_sources`, `v_recent_traces`, `v_open_curation_signals`
- [ ] 6.2 Implement `compendium/db/`: a connection helper over sync `psycopg 3` (connection from `POSTGRES_URL`) and a thin repository module with raw-SQL insert/read for `sources` and `wiki_pages`, using psycopg adapters for JSONB, arrays, UUID, and enums

## 7. Phase 1 — Verification

- [ ] 7.1 Add `tests/test_schema.py`: `alembic upgrade head` on an empty database builds the full schema; `alembic downgrade base` reverses to empty
- [ ] 7.2 Extend `tests/test_schema.py` with the round-trip smoke test: insert a stub `source` and a stub `wiki_page` through `compendium/db/`, read them back, assert equality including JSONB/array/enum columns
- [ ] 7.3 Add a test asserting the four operational views are queryable after `upgrade head`
- [ ] 7.4 **Phase 1 acceptance:** `uv run pytest` passes; `alembic upgrade head` from empty produces the full schema and `alembic downgrade base` reverses cleanly
