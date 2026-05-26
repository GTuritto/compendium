# Compendium

A personal knowledge synthesis system for one user, running locally. Compendium ingests sources (books, papers, articles, notes), synthesizes them into a canonical Markdown wiki of concept, topic, and source pages, and answers natural-language queries by retrieving from that wiki rather than from raw chunks.

The bet: a maintained wiki of stable, citable, deduplicated pages produces better answers over time than retrieval against static chunks. Every source you ingest improves every future query.

This is v0.1, single-user and local. It is not a SaaS, not multi-user, and not a chat product. See `docs/Compendium.md` for the full scope.

## Status

In development. Phases 0–9 are merged: project skeleton, the PostgreSQL schema, the ingestion pipeline, wiki page generation, the OpenSearch + Qdrant derived indexes, page-first retrieval (`compendium query`), the Memgraph structural index (`compendium graph rebuild`), operational telemetry (`compendium trace`/`page diff`/`promotions`), the Textual ops console (`compendium tui`), and the knowledge-graph curation loop (`compendium curate`). Phase 10 (golden dataset & testing) is the last remaining phase. See `docs/COMPENDIUM_BUILD.md` for the phase plan and `openspec/changes/` for change history.

## Requirements

- macOS or Linux
- [uv](https://docs.astral.sh/uv/) — Python package manager
- Python 3.12 (uv installs it if missing)
- Docker — runs the local PostgreSQL instance

## Setup

```sh
git clone <repo> compendium && cd compendium
uv sync                       # create the environment, install dependencies
docker compose up -d          # start local PostgreSQL
cp .env.example .env          # then fill in the values
uv run alembic upgrade head   # build the database schema
```

## Running

```sh
uv run python -m compendium   # validate config, print resolved storage URLs
```

## Testing

```sh
uv run pytest
```

## Configuration

- `.env` holds secrets and per-machine values: the storage URLs (`POSTGRES_URL`, `OPENSEARCH_URL`, `QDRANT_URL`, `MEMGRAPH_URL`), `VAULT_PATH`, the synthesis LLM endpoint (`SYNTHESIS_ENDPOINT`, `SYNTHESIS_MODEL`, `OPENROUTER_API_KEY`), and the embeddings endpoint (`EMBEDDINGS_ENDPOINT`, `EMBED_MODEL`). Never committed.
- `config/settings.yaml` holds non-secret behavior config (chunk sizes, retrieval thresholds, loop intervals) and references environment variables by name.

## Project layout

```text
compendium/        application package
  ingest/          source ingestion and chunking
  wiki/            page synthesis and the canonical vault
  index/           OpenSearch and Qdrant derived indexes
  retrieve/        page-first query pipeline
  graph/           Memgraph structural index
  trace/           query traces and revision tracking
  tui/             Textual ops console
  db/              PostgreSQL access layer (psycopg 3, raw SQL)
config/            non-secret behavior configuration
migrations/        Alembic migrations
tests/             test suite
vault/             the canonical Markdown wiki (versioned in git)
docs/              design and build reference documentation
Plans/             implementation plans
```

## Documentation, in reading order

1. `docs/Compendium.md` — the complete design and build reference: product vision, architecture decisions (ADRs), data contracts, the 10-phase build plan, and the testing strategy. Read it top to bottom if you are new.
2. `CLAUDE.md` — working context and architectural rules for AI coding sessions.
3. `openspec/changes/` — active change proposals, designs, specs, and task lists.
