# Tasks — phase-1-postgres-backbone

Implements Phase 1 of `docs/COMPENDIUM_BUILD.md`. Depends on `phase-0-project-skeleton` (package layout, dependencies, config loader, `docker-compose.yml`).

## 1. Alembic setup

- [x] 1.1 Run `alembic init migrations`; point `migrations/env.py` at `POSTGRES_URL` from the config loader, using a synchronous engine
- [x] 1.2 Configure Alembic for hand-written migrations (no autogenerate); set `alembic.ini` script location and naming
- [x] 1.3 Bring up the dev database (`docker compose up -d`) and confirm `alembic` connects

## 2. Schema migrations (documented 10-step order)

- [x] 2.1 Migration 1 — enums: `source_kind`, `page_kind`, `page_status`, `page_generator`, `inspection_status`, `index_kind`, `sync_state`, `promotion_kind`, `curation_signal_kind`, `curation_signal_status`
- [x] 2.2 Migration 2 — `sources` (incl. `UNIQUE (kind, content_hash)`, title GIN index) and `source_documents`
- [x] 2.3 Migration 3 — `corpus_revisions`
- [x] 2.4 Migration 4 — `chunks` (incl. `UNIQUE (source_id, body_hash)`, `chunks_source_pos_idx`)
- [x] 2.5 Migration 5 — `wiki_pages` (incl. `UNIQUE (kind, slug)`, self-FK `parent_topic_id`) and `wiki_pages_topics` M2M
- [x] 2.6 Migration 6 — `wiki_page_revisions`, its `(page_id, created_at DESC)` index, then the deferred `wiki_pages.current_revision_id` FK via `ALTER TABLE`
- [x] 2.7 Migration 7 — `index_sync_state` (incl. unique triple, partial `index_sync_pending_idx`)
- [x] 2.8 Migration 8 — `promotion_events`
- [x] 2.9 Migration 9 — `query_traces` with `query_embedding REAL[]` (nullable, no pgvector), `query_traces_corpus_idx`, partial `query_traces_fallback_idx`
- [x] 2.10 Migration 10 — `graph_curation_signals`, `graph_analysis_runs`, the deferred `run_id` FK, partial `curation_signals_open_idx`
- [x] 2.11 Ensure every migration has a correct `downgrade` reversing its `upgrade` (drop in reverse dependency order, including enums and deferred FKs)

## 3. Operational views and access layer

- [x] 3.1 Migration 11 — read-only views: `v_sync_lag`, `v_failed_sources`, `v_recent_traces`, `v_open_curation_signals`
- [x] 3.2 Implement `compendium/db/`: a connection helper over sync `psycopg 3` (connection from `POSTGRES_URL`) and a thin repository module with raw-SQL insert/read for `sources` and `wiki_pages`, using psycopg adapters for JSONB, arrays, UUID, and enums

## 4. Verification

- [x] 4.1 Add `tests/test_schema.py`: `alembic upgrade head` on an empty database builds the full schema; `alembic downgrade base` reverses to empty
- [x] 4.2 Extend `tests/test_schema.py` with the round-trip smoke test: insert a stub `source` and a stub `wiki_page` through `compendium/db/`, read them back, assert equality including JSONB/array/enum columns
- [x] 4.3 Add a test asserting the four operational views are queryable after `upgrade head`
- [x] 4.4 **Acceptance:** `uv run pytest` passes; `alembic upgrade head` from empty produces the full schema and `alembic downgrade base` reverses cleanly
