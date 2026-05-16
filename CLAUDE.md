# Compendium — Context for Claude Code Sessions

Compendium is a personal knowledge synthesis system for one user (Giuseppe Turitto), running locally on a laptop or small box. v0.1 ingests sources (books, papers, articles, notes), synthesizes them into a canonical Markdown wiki of concept, topic, and source pages, and answers natural-language queries by retrieving from that wiki rather than from raw chunks. The core bet: a maintained wiki of stable, citable, deduplicated pages produces better answers over time than retrieval against static chunks. The Textual TUI is the ops console; Obsidian is a read-only view over the same vault.

## Status

Design is complete; implementation has not started. The full design and build reference is [Compendium.md](docs/Compendium.md) — vision, 9 ADRs, data contracts, and a 10-phase build plan. Treat it as the source of truth for v0.1 scope.

As of 2026-05-16: no code exists. The first change, `bootstrap-skeleton-and-postgres` (Phase 0 + Phase 1), is scaffolded under [openspec/changes/](openspec/changes/) with proposal, design, specs, and tasks ready for implementation. Run `/opsx:apply` to begin.

## What Compendium Is

- An ingestion system: point it at a file (PDF, EPUB, Markdown, HTML) or URL; it inspects, chunks, and stores chunks with provenance. Re-ingesting is idempotent.
- A synthesis system: three page kinds — `source` (auto-generated, deterministic, one per source), `concept` (synthesized on demand, the artifact that compounds), `topic` (structural grouping). Synthesis is curator-driven.
- A page-first retrieval system: queries return a ranked list of wiki pages with chunk citations, via parallel BM25 + dense retrieval fused with reciprocal rank fusion, with chunk fallback when page coverage is thin.
- A curation system: surfaces gaps, thin grounding, contradictions, and dangling concepts as signals the user drains at their own pace.
- Fully inspectable: every query writes a trace, every page write a revision; both are persisted, queryable, and replayable.

## What Compendium Is Not (v0.1)

- Not real-time or streaming ingestion. Batch only.
- Not a chat UI and not LLM-composed answers. v0.1 output is ranked pages with citations.
- Not chunk-first RAG. Page-first; chunks are the fallback.
- Not multi-user. No auth, no permissions.
- Not a cloud deployment, SaaS, hosted service, or product.
- Not a semantic reasoning engine. Memgraph is a structural index with typed edges — no inference rules, no OWL, no SPARQL.
- Not automated semantic-edge extraction. The semantic edges are curator-driven in v0.1.

If a capability appears in an ADR but not in the Part IV build plan, it is v0.2 or later. If a feature is not on the explicit exclusion list in `docs/Compendium.md`, it has to argue its way into the next minor version. The discipline matters: Compendium risks becoming a research platform before it becomes a useful tool.

## Conventions

User communication preferences:

- Direct prose, no hedging.
- Default to prose over bullets unless a list is genuinely list-shaped.
- No em-dashes.
- No emojis unless the user uses them first.
- Minimal markdown in conversational output.

## Architectural Rules

- **The Markdown wiki is canonical (ADR-001).** Pages are plain files on disk under `vault/`, versioned and Obsidian-browseable. OpenSearch, Qdrant, and Memgraph are derived indexes; they rebuild from PostgreSQL and the vault, never the other way around.
- **PostgreSQL is the operational system of record (ADR-004).** It is the only store treated as source of truth and the only one whose schema is permanent. The schema never needs to be portable to another engine.
- **Pages are the unit of retrieval, not chunks (ADR-003).** Chunks remain only as a fallback for queries the wiki has not yet covered.
- **Synthesis is curator-driven.** The system surfaces signals; the user approves what becomes a page. No autonomous page promotion in v0.1.
- **Every query produces a trace; every page write produces a revision.** Both are persisted in PostgreSQL. Tracing is not optional.
- **Synchronous database access via `psycopg 3`.** No async DB driver. Textual offloads blocking DB work with `@work(thread=True)`; Phase 5's parallel fan-out uses `httpx` + `asyncio.gather`, independent of the DB layer.
- **Raw SQL, no ORM.** Migrations are hand-written Alembic in the documented order — no autogenerate. Queries go through a thin `compendium/db/` repository module over `psycopg 3`.
- **Native PostgreSQL enum types**, per the schema doc. Any value-set change is owned by the phase that needs it.
- **pgvector is deferred.** `query_traces.query_embedding` is `REAL[]`; vector search lives entirely in Qdrant. Adopt pgvector later only if trace-similarity analysis earns it.
- **Secrets only in `.env`.** `config/settings.yaml` holds non-secret behavior config and references env vars by name; it never contains secrets.
- **Local-first.** No SaaS observability, no telemetry, no third-party tracking. `structlog` JSON to stderr; traces to PostgreSQL.
- **Stack discipline.** Anything not in the Part IV tech-stack table is out of scope: no Kafka, no Airflow, no Redis, no production-like Docker orchestration, no separate object store. A single dev-only `docker-compose.yml` for backing stores is fine.

## Workflow

The build runs in 10 phases (below). Each phase is one OpenSpec change under `openspec/changes/`.

- For each phase, create or continue an OpenSpec change with proposal, design, specs, and tasks before implementing. Use `/opsx:propose` to scaffold and `/opsx:apply` to implement.
- Implement a phase on its own git branch named after the change (e.g. `bootstrap-skeleton-and-postgres`). Branch off the latest `main`.
- Do not move to phase N+1 until phase N's acceptance criteria pass. If a phase is taking three weeks, the scope is wrong, not the plan.
- The user reviews and merges. Do not merge to `main` yourself.
- Archive the OpenSpec change once the phase is merged and accepted.

## Build Phases (overview)

Ten phases; full detail in [Compendium.md](docs/Compendium.md) Part IV. Each ships a working slice.

- **Phase 0 — Project skeleton:** `uv` project, package layout, config loader, `structlog`, Alembic init.
- **Phase 1 — PostgreSQL operational backbone:** the full operational schema as ordered Alembic migrations.
- **Phase 2 — Ingestion pipeline:** source adapters, inspection, structure-aware chunking, idempotent storage.
- **Phase 3 — Wiki page generation:** `source`/`concept`/`topic` pages, canonical frontmatter, lint, revisions.
- **Phase 4 — Derived indexes:** OpenSearch and Qdrant populated from PostgreSQL and the vault, with sync tracking.
- **Phase 5 — Page-first retrieval:** hybrid BM25 + dense, RRF fusion, chunk fallback, full query traces.
- **Phase 6 — Memgraph structural index:** typed nodes and edges, populated and rebuildable.
- **Phase 7 — Traces and revisions:** trace inspection and replay, revision diffs, promotion events.
- **Phase 8 — TUI ops console:** keyboard-driven Textual console, one screen per operational concern.
- **Phase 9 — Knowledge graph curation loop (ADR-009):** fast per-query expansion, slow scheduled signal generation, curator UI.
- **Phase 10 — Golden dataset and testing:** golden dataset, test layers, CI.

Phases 0 and 1 are combined into the first change, `bootstrap-skeleton-and-postgres`.

## Testing

Per `docs/Compendium.md` Part V. Each phase carries acceptance criteria; do not advance until they pass.

- Test layers: unit (chunkers, lint, slug generation), integration (PostgreSQL and indexes), pipeline (ingest → page write → index → retrieval → trace), golden (fixed dataset), graph-specific (expansion, signal generation).
- `uv run pytest` runs the suite. Golden runs as a slower nightly job.
- The golden dataset is the regression and quality signal: a handful of sources of varying difficulty, queries with expected page candidates, and queries with expected chunk-fallback behavior.

## Development Environment

- OS: macOS 25.4.0
- Shell: /bin/zsh
- Path format: Unix
- Line endings: LF
- Package manager: `uv`; Python 3.12
- Backing stores run locally via a dev-only `docker-compose.yml`
