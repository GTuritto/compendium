# Compendium — Context for Claude Code Sessions

Compendium is a personal knowledge synthesis system for one user (Giuseppe Turitto), running locally on a laptop or small box. v0.1 ingests sources, both what you read (books, papers, articles, web) and what you write (your own notes, essays, and drafts), synthesizes them into a canonical Markdown wiki of concept, topic, and source pages, and answers natural-language queries by retrieving from that wiki rather than from raw chunks. The core bet: a maintained wiki of stable, citable, deduplicated pages produces better answers over time than retrieval against static chunks. The Textual TUI is the ops console; Obsidian is a read-only view over the same vault.

## Status

Design is complete and the build is underway. The design source of truth is [Compendium.md](docs/Compendium.md) — vision, 9 ADRs, data contracts, the build plan. The build process source of truth is [COMPENDIUM_BUILD.md](docs/COMPENDIUM_BUILD.md) — the 11 phases, the per-phase workflow, branch names, and resolved decisions.

As of 2026-05-25: Phases 0 through 5 are implemented and merged to `main`; Phase 6 is in progress on `phase-6-memgraph` (PR #11).

- **Phase 0 — Project skeleton** (merged): `uv` project, package layout, config loader, `structlog`, dev `docker-compose.yml`.
- **Phase 1 — PostgreSQL backbone** (merged): all 11 ordered Alembic migrations (`0001_enums` → `0011_operational_views`).
- **Phase 2 — Ingestion** (merged): adapters, inspection, structure-aware chunking, idempotent storage, `compendium ingest`. Includes the BUG-001 fix (missing-path ingest returns a failed result, not a crash).
- **Phase 3 — Wiki generation** (merged): `source`/`concept`/`topic` pages, canonical frontmatter, lint, vault writer, revisions.
- **Phase 4 — Derived indexes** (merged): OpenSearch and Qdrant populated from PostgreSQL and the vault, embedding seam, sync worker, `compendium reindex`/`index` CLI.
- **Phase 5 — Page-first retrieval** (merged, PR #8): async OpenSearch + Qdrant fan-out, RRF fusion, normalized top-page coverage, chunk fallback with gap flagging, full query-trace persistence, `compendium query` CLI.
- **Phase 6 — Memgraph structural index** (in progress, PR #11): four node types and the automatic `PART_OF`/`EVIDENCES`/`GROUNDS` edges populated from PostgreSQL + the vault, the `memgraph` sync kind, `compendium graph rebuild`/`status`. neo4j Bolt driver, no OGM.

**Phase 7 — Traces and revisions (`phase-7-traces`) is next** once Phase 6 merges. The directories for Phases 7–8 ([compendium/trace/](compendium/trace/), [compendium/tui/](compendium/tui/)) are still stubs; Phases 9–10 are unstarted.

Resolved build decisions: embedding model is BGE-M3 (`BAAI/bge-m3`); vault layout is the structured `vault/{concepts,topics,sources}/`; synthesis defaults to OpenRouter with Claude Sonnet 4.5; Compendium runs on the laptop. Dev backing-store host ports are remapped to avoid collisions with a local bibliomind stack: Qdrant on **6533/6534** and Memgraph on **7688/7445** (containers still listen on the defaults internally). The graph layer uses the `neo4j` Bolt driver with raw Cypher (no OGM), the analog of `compendium/db/` over `psycopg`.

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

The build runs in 11 phases (0–10), defined in [COMPENDIUM_BUILD.md](docs/COMPENDIUM_BUILD.md). Phases are strictly ordered: never start phase N+1 before phase N is merged. Each phase carries two spec artifacts — an **OpenSpec change** (`openspec/changes/phase-N-<name>/`: the requirement contract) and a **Phase Plan** (`Plans/phase-N-<name>.md`: the execution breakdown).

The per-phase loop:

1. **Branch** — `git checkout -b phase-N-<name>` off the latest `main`.
2. **OpenSpec change** — create the change with proposal, design, specs, tasks (`/opsx:propose`).
3. **Phase Plan** — author `Plans/phase-N-<name>.md` from [Plans/_TEMPLATE-phase-plan.md](Plans/_TEMPLATE-phase-plan.md): sub-phases, tasks, the per-phase smoke test, open questions.
4. **Review gate** — the user revises and approves the Phase Plan. No implementation code is written until it is approved.
5. **Draft PR** — after the first commit, open a draft PR against `main`, titled `Phase N — <Title>`, body linking the Phase Plan.
6. **Implement** — one commit per sub-phase (`Phase Na — <sub-phase>`), green at HEAD; final commit `Phase N complete — <short title>`. Append the phase's smoke test to [tests/manual/smoke_test.md](tests/manual/smoke_test.md).
7. **Verify** — run the phase's testing plan and smoke test; mark the PR ready for review.
8. **Merge** — the user reviews and merges. Do not merge to `main` yourself.

Every commit ends with the trailer `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`. If a phase takes more than two focused weekends, the scope is wrong, not the plan.

## Build Phases (overview)

Eleven phases (0–10); branch names and verbatim Goal/Acceptance in [COMPENDIUM_BUILD.md](docs/COMPENDIUM_BUILD.md). Each ships a working slice.

- **Phase 0 — Project skeleton** (`phase-0-project-skeleton`): `uv` project, package layout, config loader, `structlog`, dev `docker-compose.yml`.
- **Phase 1 — PostgreSQL operational backbone** (`phase-1-postgres-backbone`): the full operational schema as ordered Alembic migrations.
- **Phase 2 — Ingestion pipeline** (`phase-2-ingestion`): source adapters, inspection, structure-aware chunking, idempotent storage.
- **Phase 3 — Wiki page generation** (`phase-3-wiki-generation`): `source`/`concept`/`topic` pages, canonical frontmatter, lint, revisions.
- **Phase 4 — Derived indexes** (`phase-4-derived-indexes`): OpenSearch and Qdrant populated from PostgreSQL and the vault, with sync tracking.
- **Phase 5 — Page-first retrieval** (`phase-5-retrieval`): hybrid BM25 + dense, RRF fusion, chunk fallback, full query traces.
- **Phase 6 — Memgraph structural index** (`phase-6-memgraph`): typed nodes and edges, populated and rebuildable.
- **Phase 7 — Traces and revisions** (`phase-7-traces`): trace inspection and replay, revision diffs, promotion events.
- **Phase 8 — TUI ops console** (`phase-8-tui`): keyboard-driven Textual console, one screen per operational concern.
- **Phase 9 — Knowledge graph curation loop** (`phase-9-curation-loop`, ADR-009): fast per-query expansion, slow scheduled signal generation, curator UI.
- **Phase 10 — Golden dataset and testing** (`phase-10-testing`): golden dataset, test layers, CI.

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
