## Context

This change implements Phase 1 (PostgreSQL operational backbone) of the build plan in `docs/COMPENDIUM_BUILD.md`. It builds on `phase-0-project-skeleton`, which established the `uv` project, the package layout, the config loader, and the dev `docker-compose.yml`.

PostgreSQL is the permanent operational system of record (ADR-004) — the schema never needs to be portable to another engine. The authoritative schema overview is in `docs/Compendium.md` Part III; this change translates it into migrations and an access layer.

The foundational decisions — synchronous access via `psycopg 3`, and raw SQL with no ORM — were made in `phase-0-project-skeleton` and are not re-litigated here. This document covers the decisions specific to the schema.

## Goals / Non-Goals

**Goals:**

- The complete operational PostgreSQL schema as ordered, hand-written Alembic migrations that apply and reverse cleanly.
- A synchronous `psycopg 3` access layer thin enough to read like the schema doc.

**Non-Goals:**

- Populating the schema with real data — that is Phase 2 (ingestion).
- Connecting to OpenSearch, Qdrant, or Memgraph.
- An ORM, async I/O, or pgvector — explicitly excluded below.

## Decisions

### Decision: Hand-written migrations, no autogenerate

The schema leans on PostgreSQL-native features autogenerate handles badly — native `ENUM` types, partial indexes (`WHERE state = 'pending'`), GIN indexes, `TEXT[]`/`REAL[]` arrays, four views, and a deferred circular `wiki_pages ↔ wiki_page_revisions` FK. `docs/Compendium.md` already prescribes a fixed 10-step migration order, which is a hand-authored sequence. Migrations are therefore written by hand with `op.execute`. Autogenerate would be fought, not used.

### Decision: Native PostgreSQL enum types

`docs/Compendium.md` specifies `CREATE TYPE ... AS ENUM` for all ten enums; this change follows it. Native enums are known to be awkward to alter later, but the enum value sets are stable design contracts. If a value set must change in a later phase, that phase owns the `ALTER TYPE` migration.

### Decision: Defer pgvector — `query_traces.query_embedding` is `REAL[]`

Over `CREATE EXTENSION vector` + `VECTOR(1024)`. This column persists the query embedding for trace replay (Phase 7); vector *search* happens entirely in Qdrant, never in Postgres. `VECTOR(n)` would hardcode an embedding dimension into the schema even though `EMBED_MODEL` is configurable, and would add a Postgres extension requirement that constrains provisioning. `docs/Compendium.md` explicitly sanctions this fallback. A plain `REAL[]` stores the float32 vector for replay without coupling or extra dependencies; adopting pgvector later is a clean migration if trace-similarity analysis ever earns its place.

### Decision: Resolve the circular FK with a deferred `ALTER TABLE`

`wiki_pages.current_revision_id` references `wiki_page_revisions(id)`, and `wiki_page_revisions.page_id` references `wiki_pages(id)`. The migration creating `wiki_page_revisions` (step 6) adds the `wiki_pages.current_revision_id` FK via `ALTER TABLE` after both tables exist. The same pattern applies to `graph_curation_signals.run_id` referencing `graph_analysis_runs` (step 10).

## Risks / Trade-offs

- **Hand-written migrations drift from the schema doc** → The smoke test inserts and reads a `source` and a `wiki_page` exercising JSONB/array/enum columns; `upgrade`+`downgrade` is asserted, catching ordering and reversal errors.
- **Raw SQL typos surface at runtime, not at construction** → All SQL is confined to `compendium/db/`; the round-trip test covers the inserted columns.
- **Native enums are painful to alter** → Accepted; value sets are stable contracts, and any change is owned by the phase that needs it.

## Migration Plan

Local: with the dev Postgres running (`docker compose up -d`), `uv run alembic upgrade head` builds the schema. Rollback is `uv run alembic downgrade base`, which the spec requires to be clean.

## Open Questions

- Test isolation strategy — a disposable database per run vs. transaction rollback per test vs. testcontainers — is left to Phase 10's testing change. Phase 1 uses a simple round-trip test against the dev database.
