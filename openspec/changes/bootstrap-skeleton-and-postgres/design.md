## Context

Compendium is documented in a single 127KB reference (`docs/Compendium.md`) — vision, 9 ADRs, data contracts, and a 10-phase build plan — but no code exists. This change implements Phase 0 (project skeleton) and Phase 1 (PostgreSQL operational backbone) of that plan.

The design doc fixes the high-level stack (Python 3.12, `uv`, PostgreSQL 16, Alembic, `structlog`) but deliberately leaves several foundational choices open ("asyncpg or psycopg if staying sync"; "pgvector if installed"). Those choices color every later phase, so they are decided here. The decisions below were settled in a design interview and are recorded so later phases inherit them without re-litigation.

Constraints: single user, single machine, batch workloads, no concurrency pressure, local-first (no SaaS dependencies). PostgreSQL is the permanent operational system of record (ADR-004) — the schema never needs to be portable to another engine.

## Goals / Non-Goals

**Goals:**

- A `uv`-managed Python 3.12 project that starts via `python -m compendium`, validates configuration, and exits cleanly.
- The complete operational PostgreSQL schema as ordered, hand-written Alembic migrations that apply and reverse cleanly.
- A synchronous `psycopg 3` access layer thin enough to read like the schema doc.
- Foundational technical decisions made explicitly so Phases 2–10 inherit them.

**Non-Goals:**

- Connecting to OpenSearch, Qdrant, or Memgraph. Their URLs appear in `.env.example` and are printed at startup, but no client is built (Phases 4 and 6).
- Ingestion, synthesis, retrieval, the TUI, or any worker loop.
- An ORM, async I/O, or pgvector — explicitly excluded below.
- A production or multi-service deployment.

## Decisions

### Decision: Synchronous database access via `psycopg 3`

Over async (`asyncpg`). Single-user batch workloads have no throughput need. The only real async pressure is Textual (Phase 8), which runs an asyncio loop — and Textual supports `@work(thread=True)` to push blocking DB calls off the UI loop. Phase 5's "parallel fan-out" to OpenSearch and Qdrant is two HTTP calls, handled with `httpx` + `asyncio.gather` independently of the DB driver. Async would impose function-coloring across the whole codebase for concurrency that never gets collected, and would require a second (sync) driver config for Alembic anyway.

*Trade-off:* if Compendium ever outgrows single-user, an async retrofit is costly — but multi-user is an explicit non-goal of the whole project.

### Decision: Raw SQL, hand-written migrations, no ORM

Over SQLAlchemy ORM or Core. The schema leans on PostgreSQL-native features — native `ENUM` types, partial indexes (`WHERE state = 'pending'`), GIN indexes, `TEXT[]`/`REAL[]` arrays, four views, and a deferred circular FK. Alembic autogenerate handles none of these reliably, and the design doc already prescribes a fixed 10-step migration order, which is a hand-authored sequence. Migrations are therefore written by hand with `op.execute`. Queries go through a thin `compendium/db/` repository module over `psycopg 3`, whose adapters handle JSONB, arrays, UUID, and enums natively. An ORM's identity map, lazy loading, and session lifecycle are pure overhead for a single-user batch CRUD layer; Core's dialect portability is worthless when Postgres is the permanent store.

*Trade-off:* raw SQL strings are easier to mistype than a typed table registry. Mitigation: concentrate all SQL in `compendium/db/` and cover it with the Phase 1 round-trip smoke test.

### Decision: Defer pgvector — `query_traces.query_embedding` is `REAL[]`

Over `CREATE EXTENSION vector` + `VECTOR(1024)`. This column persists the query embedding for trace replay (Phase 7); vector *search* happens entirely in Qdrant, never in Postgres. `VECTOR(n)` would hardcode an embedding dimension into the schema even though `EMBED_MODEL` is a configurable variable, and it would add a Postgres extension requirement that constrains provisioning. The design doc explicitly sanctions this fallback. A plain `REAL[]` stores the float32 vector for replay without coupling or extra dependencies; adopting pgvector later is a clean migration if trace-similarity analysis ever earns its place.

### Decision: Native PostgreSQL enum types

The design doc specifies `CREATE TYPE ... AS ENUM` for all ten enums; this change follows it. Native enums are known to be awkward to alter later, but the enum value sets are stable design contracts, and matching the doc keeps the schema authoritative. If a value set must change in a later phase, that phase owns the `ALTER TYPE` migration.

### Decision: Dev Postgres via a single-service `docker-compose.yml`

Over a native Homebrew install or a documented `docker run`. A pinned `postgres:16` image gives every developer and CI run an identical version; `docker compose up -d` is one declarative command. The design doc's "no Docker Compose" exclusion targets production-like multi-service orchestration — a single dev database service is not that. The same file is the natural home for the OpenSearch/Qdrant/Memgraph services that later changes will append.

### Decision: Config validation is parse/resolve only

`python -m compendium` validates that required env vars are present and that `settings.yaml` parses and its env references resolve. It does not open connections — Phase 0 predates any DB. Connectivity is exercised by the Phase 1 round-trip smoke test instead. This keeps the entrypoint fast and usable before any backend is running.

## Risks / Trade-offs

- **Hand-written migrations drift from the schema doc** → The Phase 1 smoke test inserts and reads a `source` and a `wiki_page` exercising JSONB/array/enum columns; `upgrade`+`downgrade` is asserted in CI-style test, catching ordering and reversal errors.
- **Raw SQL typos surface at runtime, not at construction** → All SQL is confined to `compendium/db/`; the round-trip test covers the inserted columns.
- **The four foundational decisions deviate from or sharpen the design doc** → Each deviation (sync, no ORM, `REAL[]`) is recorded here with rationale so later phases and the doc reconcile against a single source.
- **Native enums are painful to alter** → Accepted; value sets are stable contracts, and any change is owned by the phase that needs it.
- **`docker-compose.yml` wording tension with the doc** → Accepted deliberately; the exclusion is about production-like stacks, and the single-service file is documented as dev-only.

## Migration Plan

This is greenfield — there is no existing system to migrate from or roll back to. Deployment is local: `git init`, `uv sync`, `docker compose up -d`, `cp .env.example .env` and fill values, `alembic upgrade head`. Rollback of the schema is `alembic downgrade base`, which the spec requires to be clean.

## Open Questions

- Should later non-Postgres stores (OpenSearch, Qdrant, Memgraph) join the same `docker-compose.yml`, or get separate files? Deferred to the changes that introduce them (Phases 4, 6).
- Test isolation strategy — a disposable database per run vs. transaction rollback per test vs. testcontainers — is left to Phase 10's testing change. Phase 1 uses a simple round-trip test against the dev database.
