## Context

Compendium is documented in `docs/Compendium.md` — vision, 9 ADRs, data contracts, and a 10-phase build plan — but no code exists. This change implements Phase 0 (project skeleton) of that plan.

`docs/Compendium.md` fixes the high-level stack (Python 3.12, `uv`, PostgreSQL 16, Alembic, `structlog`) but deliberately leaves some foundational choices open ("asyncpg or psycopg if staying sync"). Those choices color every later phase, so the foundational ones are decided here. The decisions were settled in a design interview and are recorded so later phases inherit them without re-litigation.

Constraints: single user, single machine, batch workloads, no concurrency pressure, local-first (no SaaS dependencies).

## Goals / Non-Goals

**Goals:**

- A `uv`-managed Python 3.12 project that starts via `python -m compendium`, validates configuration, and exits cleanly.
- Foundational technical decisions made explicitly so Phases 1–10 inherit them.

**Non-Goals:**

- The database schema and migrations — that is Phase 1 (`phase-1-postgres-backbone`).
- Connecting to any storage backend. URLs are resolved and printed; no client is built.
- Ingestion, synthesis, retrieval, the TUI, or any worker loop.

## Decisions

### Decision: Synchronous database access via `psycopg 3`

Over async (`asyncpg`). Single-user batch workloads have no throughput need. The only real async pressure is Textual (Phase 8), which runs an asyncio loop and supports `@work(thread=True)` to push blocking DB calls off the UI loop. Phase 5's parallel fan-out to OpenSearch and Qdrant is two HTTP calls, handled with `httpx` + `asyncio.gather` independently of the DB driver. Async would impose function-coloring across the whole codebase for concurrency that never gets collected, and would require a second sync driver config for Alembic anyway. This change therefore adds `psycopg[binary]` (v3) as the database dependency; `compendium/db/` is built in Phase 1.

### Decision: Raw SQL, no ORM

Over SQLAlchemy ORM or Core. The Phase 1 schema leans on PostgreSQL-native features that an ORM and Alembic autogenerate handle badly. Queries will go through a thin `compendium/db/` repository module over `psycopg 3`. An ORM's identity map, lazy loading, and session lifecycle are pure overhead for a single-user batch system; portability is worthless when Postgres is the permanent store. Phase 0 reflects this by *not* adding SQLAlchemy as a direct dependency (Alembic pulls it in transitively, for Phase 1).

### Decision: Config validation is parse/resolve only

`python -m compendium` validates that required env vars are present and that `settings.yaml` parses and its env references resolve. It does not open connections — Phase 0 predates any database. Connectivity is exercised by Phase 1's smoke test. This keeps the entrypoint fast and usable before any backend is running.

### Decision: Dev Postgres via a single-service `docker-compose.yml`

Over a native Homebrew install or a documented `docker run`. A pinned `postgres:16` image gives every developer and CI run an identical version; `docker compose up -d` is one declarative command. `docs/Compendium.md`'s "no Docker Compose" exclusion targets production-like multi-service orchestration — a single dev database service is not that. The same file is the natural home for the OpenSearch/Qdrant/Memgraph services that later phases will append. Phase 0 creates the file with only the Postgres service.

### Decision: Native PostgreSQL enum types and pgvector are deferred to Phase 1

Phase 0 does not create schema, so the enum and pgvector decisions belong to `phase-1-postgres-backbone`. They are noted here only to mark the boundary.

## Risks / Trade-offs

- **The foundational decisions (sync, no ORM) constrain later phases** → Each is recorded here with rationale so later phases reconcile against a single source rather than re-deciding.
- **`docker-compose.yml` wording tension with `docs/Compendium.md`** → Accepted deliberately; the exclusion is about production-like stacks, and the file is documented as dev-only.

## Migration Plan

Greenfield — no existing system. Local setup: `git init`, `uv sync`, `cp .env.example .env` and fill values, `docker compose up -d`. No rollback concern; the change adds files only.

## Open Questions

- Embedding model, host, and vault layout are open per `docs/Compendium.md` but do not block Phase 0; they are tracked in `docs/COMPENDIUM_BUILD.md`.
