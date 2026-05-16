# Phase 1 — PostgreSQL operational backbone: Implementation Plan

Date: 2026-05-16
Branch: `phase-1-postgres-backbone` (off `main`)
OpenSpec change: `openspec/changes/phase-1-postgres-backbone/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 1;
[docs/Compendium.md](../docs/Compendium.md) Part III (PostgreSQL schema).

## Goal

The full operational PostgreSQL schema exists as ordered, hand-written Alembic
migrations. `alembic upgrade head` from an empty database builds the whole
schema; `alembic downgrade base` reverses it cleanly. A `psycopg 3` access
layer can round-trip a stub `source` and `wiki_page`.

## Why this plan exists

It fixes the migration breakdown, the `compendium/db/` module structure, and
the test-database strategy before any DDL is written, so the 11 migrations and
the access layer land in a reviewable, dependency-correct order.

## Branch + commit strategy

- Branch `phase-1-postgres-backbone` off `main` (done).
- One commit per sub-phase (1a–1g), each green at HEAD: after every migration
  sub-phase, `alembic upgrade head` and `alembic downgrade base` both succeed.
- First commit is this plan; draft PR `Phase 1 — PostgreSQL operational
  backbone` opened against `main` after it.
- Final commit: `Phase 1 complete — PostgreSQL operational backbone`.
- Every commit ends with
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- User reviews and merges.

## Prerequisite

The dev database must be running: `docker compose up -d` (the `postgres:16`
service from Phase 0). Migrations and the integration test need it.

## Sub-phases

### 1a — Alembic setup

**Purpose:** A working sync Alembic configured for hand-written migrations.

**Tasks:**

1. `uv run alembic init migrations` (populates `migrations/`, removes the
   placeholder `.gitkeep`; writes `alembic.ini` at the repo root).
2. Rewrite `migrations/env.py`: obtain `POSTGRES_URL` from
   `compendium.config.load_config()`, use a synchronous engine, run migrations
   offline and online. No autogenerate / `target_metadata` stays `None`.
3. Set `alembic.ini` script location and a timestamped revision file template.

**Files added:** `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`.
**Files modified:** `migrations/.gitkeep` removed.

**Decision flagged:** migrations are hand-written; autogenerate is not used.

### 1b — Migrations 1–2: enums and source tables

**Purpose:** The ten enum types and the `sources` / `source_documents` tables.

**Tasks:**

1. Migration 1 — `CREATE TYPE` for `source_kind`, `page_kind`, `page_status`,
   `page_generator`, `inspection_status`, `index_kind`, `sync_state`,
   `promotion_kind`, `curation_signal_kind`, `curation_signal_status`.
2. Migration 2 — `sources` (incl. `UNIQUE (kind, content_hash)`, title GIN
   index) and `source_documents` (FK to `sources`, `ON DELETE CASCADE`).
3. Each migration has a `downgrade` reversing it.

**Files added:** `migrations/versions/0001_*.py`, `0002_*.py`.

### 1c — Migrations 3–6: corpus, chunks, wiki pages

**Purpose:** Corpus revisions, chunks, and the wiki page tables, including the
circular foreign key.

**Tasks:**

1. Migration 3 — `corpus_revisions`.
2. Migration 4 — `chunks` (`UNIQUE (source_id, body_hash)`, `chunks_source_pos_idx`).
3. Migration 5 — `wiki_pages` (`UNIQUE (kind, slug)`, self-FK `parent_topic_id`)
   and `wiki_pages_topics` (M2M).
4. Migration 6 — `wiki_page_revisions`, its `(page_id, created_at DESC)` index,
   then the deferred `wiki_pages.current_revision_id` FK via `ALTER TABLE`.

**Files added:** `migrations/versions/0003_*.py` … `0006_*.py`.

### 1d — Migrations 7–10: operational and graph tables

**Purpose:** Index sync state, promotion events, query traces, and the graph
curation tables.

**Tasks:**

1. Migration 7 — `index_sync_state` (unique triple, partial `index_sync_pending_idx`).
2. Migration 8 — `promotion_events`.
3. Migration 9 — `query_traces` with `query_embedding REAL[]` (nullable, no
   pgvector), `query_traces_corpus_idx`, partial `query_traces_fallback_idx`.
4. Migration 10 — `graph_curation_signals`, `graph_analysis_runs`, the deferred
   `run_id` FK, partial `curation_signals_open_idx`.

**Files added:** `migrations/versions/0007_*.py` … `0010_*.py`.

### 1e — Migration 11: operational views

**Purpose:** The four read-only TUI views.

**Tasks:**

1. Migration 11 — `CREATE VIEW` for `v_sync_lag`, `v_failed_sources`,
   `v_recent_traces`, `v_open_curation_signals`; `downgrade` drops them.

**Files added:** `migrations/versions/0011_*.py`.

### 1f — Database access layer

**Purpose:** A thin synchronous `psycopg 3` layer, no ORM.

**Tasks:**

1. `compendium/db/connection.py`: a `connect()` helper / context manager that
   opens a sync `psycopg` connection from `config.postgres_url`.
2. `compendium/db/repository.py`: raw-SQL `insert` and `get` functions for
   `sources` and `wiki_pages`, using psycopg type adapters for JSONB, arrays,
   UUID, and enums.

**Files added:** `compendium/db/connection.py`, `compendium/db/repository.py`.

### 1g — Tests and acceptance

**Purpose:** Lock schema behavior with an integration test; verify acceptance.

**Tasks:**

1. `tests/test_schema.py`: against the test database (see Open Question 1),
   `alembic upgrade head` builds the full schema; the four views are queryable;
   a stub `source` and `wiki_page` round-trip through `compendium/db/`;
   `alembic downgrade base` leaves an empty schema. The test skips with a clear
   message if Postgres is unreachable.
2. Run `uv run pytest` and smoke scenarios 1.1–1.5.

**Files added:** `tests/test_schema.py`.

## Final file tree after Phase 1

```text
alembic.ini                      new
migrations/
  env.py                         new
  script.py.mako                 new
  versions/
    0001_enums.py                new
    0002_sources.py              new
    0003_corpus_revisions.py     new
    0004_chunks.py               new
    0005_wiki_pages.py           new
    0006_wiki_page_revisions.py  new
    0007_index_sync_state.py     new
    0008_promotion_events.py     new
    0009_query_traces.py         new
    0010_graph_curation.py       new
    0011_operational_views.py    new
compendium/db/
  connection.py                  new
  repository.py                  new
tests/test_schema.py             new
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | integration | Upgrade | `alembic upgrade head` on an empty DB builds every table, enum, and view. |
| 2 | integration | Downgrade | `alembic downgrade base` leaves an empty schema. |
| 3 | integration | Round-trip | A stub `source` and `wiki_page` insert and read back equal, incl. JSONB/array/enum columns. |
| 4 | integration | Views | The four `v_*` views are queryable after `upgrade head`. |

`uv run pytest` runs the suite; the Phase 1 test skips when Postgres is
unreachable so the suite still passes without Docker.

## Per-phase smoke test

Scenarios 1.1–1.5 are drafted in
[tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 1 (dev
database up, upgrade builds the schema, downgrade reverses, stub round-trip,
views queryable). Sub-phase 1g runs them; refine the table if any command
changes.

## Out of scope for Phase 1 (do NOT build)

- Ingestion, chunking, or any source adapter (Phase 2).
- Populating the schema with real data; repository functions beyond `sources`
  and `wiki_pages` insert/read.
- OpenSearch, Qdrant, Memgraph, or `index_sync_state` workers.
- pgvector — `query_traces.query_embedding` is `REAL[]`.
- Test isolation via testcontainers (Phase 10).

## Open questions to confirm before starting

1. **Test database.** The schema test needs a database to upgrade and
   downgrade. *Recommendation: a dedicated `compendium_test` database.* The test
   connects to the `postgres` maintenance database, drops and recreates
   `compendium_test` for a clean slate, and runs migrations there. This keeps
   the dev `compendium` database untouched. Derive its URL from `POSTGRES_URL`
   (swap the database name). The alternative, running the test against the dev
   `compendium` database, is simpler but `downgrade base` would wipe it.

2. **`compendium/db/` structure.** *Recommendation:* `connection.py` for the
   connection helper and a single `repository.py` for the `sources` and
   `wiki_pages` insert/read functions. Phase 2+ can split `repository.py` per
   entity as it grows. Confirm or prefer per-entity modules now.

## Definition of done for Phase 1

- [ ] Sub-phases 1a–1g committed, green at HEAD.
- [ ] OpenSpec change `phase-1-postgres-backbone` tasks checked off.
- [ ] `uv run pytest` passes.
- [ ] Smoke scenarios 1.1–1.5 pass.
- [ ] Acceptance: `alembic upgrade head` from empty builds the full schema;
      `alembic downgrade base` reverses cleanly; the stub round-trip works.
- [ ] Draft PR `Phase 1 — PostgreSQL operational backbone` marked ready.
