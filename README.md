<p align="center">
  <img src="docs/logo.png" alt="Compendium logo" width="320">
</p>

# Compendium

A personal knowledge synthesis system for one user, running locally. Compendium ingests sources (books, papers, articles, notes), synthesizes them into a canonical Markdown wiki of concept, topic, and source pages, and answers natural-language queries by retrieving from that wiki rather than from raw chunks.

The bet: a maintained wiki of stable, citable, deduplicated pages produces better answers over time than retrieval against static chunks. Every source you ingest improves every future query.

Single-user and local. It is not a SaaS, not multi-user, and not a chat product. See [`docs/Compendium.md`](docs/Compendium.md) for the full scope and the ADRs, and [`docs/DECISIONS.md`](docs/DECISIONS.md) for a consolidated record of every significant decision and why it was made.

**New here? Start with the [Instruction Manual](docs/MANUAL.md)** — how to install, how to use it day to day, and how to connect another system (your agents, scripts, or apps) to Compendium as long-term memory. To understand *how it works* — the principles and what each operation actually does — read [`docs/PRINCIPLES.md`](docs/PRINCIPLES.md).

## Status

v0.1 is feature-complete. All eleven phases (0–10) are merged: project skeleton, the PostgreSQL schema, the ingestion pipeline, wiki page generation, the OpenSearch + Qdrant derived indexes, page-first retrieval (`compendium query`), the Memgraph structural index (`compendium graph rebuild`), operational telemetry (`compendium trace`/`page diff`/`promotions`), the Textual ops console (`compendium tui`), the knowledge-graph curation loop (`compendium curate`), and the golden dataset & testing tier with CI (Phase 10). See `docs/COMPENDIUM_BUILD.md` for the v0.1 phase plan and `openspec/changes/` for change history.

v0.2 is feature-complete (all eight phases merged). **Phase 1 — Real-model validation** is merged (PR #30, 2026-05-30): the `live` pytest tier exercises real OpenRouter / BGE-M3 calls on demand, a per-host model strategy lives at [`docs/operations/real-models.md`](docs/operations/real-models.md), and the embedder seam now accepts an `EMBEDDINGS_API_KEY`. **Phase 2 — Backup / restore** ships `compendium backup` / `compendium restore` for PostgreSQL + vault snapshots, optional off-host rsync to `BACKUP_RSYNC_DEST`, and a scheduled daily-at-02:00 unit via `compendium backup install`. See [`docs/operations/backup-restore.md`](docs/operations/backup-restore.md). **Phase 3 — Scheduled curation daemon** (ships ADR-012) adds `compendium schedule install [--every 1h]` to fire `compendium curate run` on a per-OS user-level timer (launchd / systemd) with `schedule status` / `schedule uninstall` companions. See [`docs/operations/schedule.md`](docs/operations/schedule.md). **Phase 4 — Ingestion automation (inbox)** ships `compendium inbox install [--path ~/Compendium/inbox]` — files dropped under `inbox/<kind>/` auto-ingest with that kind and route to `inbox/processed/<YYYY-MM-DD>/` on success or `inbox/failed/<YYYY-MM-DD>/` (with a `.error` sidecar) on parse failure. See [`docs/operations/inbox.md`](docs/operations/inbox.md). **Phase 5 — Retrieval tuning** adds rule-based query normalization (lowercase + stop-words + alias expansion) in the `query` hot path, an OpenSearch `compendium_text` analyzer with an inline synonym filter sourced from page aliases, Qdrant HNSW parameters threaded through search, and a captured per-query metric baseline at `tests/golden/baseline.json`. See [`docs/operations/retrieval-tuning.md`](docs/operations/retrieval-tuning.md). **Phase 6 — Composed answers (`ask`)** adds `compendium ask "<question>"`: an LLM-composed answer over the top-K pages with structured page-anchored citations, a refusal mode below `ask.refuse_below_coverage` (default 0.3), an LLM query rewrite (Shape D part 2), streaming text output, and its own `ask_traces` row joined to `query_traces`. See [`docs/operations/ask.md`](docs/operations/ask.md). **Phase 7 — Access surface (MCP + HTTP)** (ships ADR-011) makes Compendium callable by colocated agents: `compendium serve` runs a FastAPI server on `127.0.0.1` (no auth) and `compendium mcp` runs an MCP stdio server, both over one shared facade exposing six verbs (`query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status`); access-surface `ingest` accepts raw bytes and auto-runs `index sync`, and `ask` streams. See [`docs/operations/access-surface.md`](docs/operations/access-surface.md). **Phase 8 — Autonomous semantic-edge extraction** (ships ADR-010) adds a slow-loop generator that, per changed page, pulls Qdrant neighbours and asks the LLM (one call per page) to label pairs, writing `RELATED_TO`/`PREREQUISITE_FOR` edges into Memgraph with provenance (`extracted_by`, `confidence`, `weight`) above a confidence threshold; curator edges are never overwritten and the fast-loop expansion densifies without curator effort. See [`docs/operations/edge-extraction.md`](docs/operations/edge-extraction.md). The v0.2 plan is in [`docs/COMPENDIUM_V0.2_BUILD.md`](docs/COMPENDIUM_V0.2_BUILD.md).

v0.3 is complete: curator-approved contradiction suggestions (ADR-014) and the
loopback Streamlit web UI (ADR-015) shipped on 2026-06-12. v0.4 validation is
active: Phase 0 cleared obsolete validation machinery, Phase 1 shipped the
chunk-only A/B control arm (ADR-016), and Track A is accumulating real-corpus
queries. See [`docs/COMPENDIUM_V0.4_BUILD.md`](docs/COMPENDIUM_V0.4_BUILD.md),
[`docs/operations/track-a.md`](docs/operations/track-a.md), and
[`docs/operations/validation.md`](docs/operations/validation.md).

**Deploying on a personal host:** `deploy/install.sh` is a one-shot deployer (prereqs → `uv sync` → docker stores → migrations → reindex → install the four launchd/systemd services), and `deploy/compendiumctl {start|stop|status|restart|logs}` drives the running stack (`compendium start|stop|restart` are thin CLI adapters over it). The access surface now has its own always-on unit (`compendium serve install`), closing the ADR-012 access-surface-daemon gap. See [`docs/operations/deployment.md`](docs/operations/deployment.md) and the install section below. The distribution is built by a smoke-gated CI pipeline: on every `main` push the `smoke` job runs the full suite plus a scripted end-to-end walk (`deploy/ci-smoke.sh`), and only when it is green does the `distribution` job build and upload the bundle — a `v*` tag publishes it as a GitHub Release. A post-v0.2 **local profiler** (PR #63) adds opt-in, stdlib-only performance / CPU / memory debugging: `compendium profile stats` aggregates read-only over the persisted traces, the global `--timings` / `--profile` flags instrument one invocation, and SIGUSR1/SIGUSR2 arm/report a tracemalloc diff in the serve daemon. See [`docs/operations/profiling.md`](docs/operations/profiling.md).

## Install from the distribution

The distribution is **two files that sit side by side**:

```text
install.sh                 the interactive installer
compendium-deploy.zip      the payload bundle (app, migrations, config, compose files)
```

Get them from any of:

1. **A GitHub Release** — published automatically for every `v*` tag, after the
   CI smoke gate passes (recommended for installs).
2. **A CI workflow artifact** — every push to `main` uploads
   `compendium-deploy-<version>-<sha>` from the `distribution` job (gated on the
   same smoke pass).
3. **The repo itself** — the committed [`2Deploy/`](2Deploy/) folder, refreshed
   from `main`; or rebuild it locally with `deploy/make-bundle.sh`.

**Requirements on the target machine:** Docker Engine + Compose v2, `unzip`,
about 4 GB of free RAM for the four backing stores, and — for the host-native
mode — `uv` (the installer offers to install it). Outbound internet only if you
use OpenRouter for synthesis/embeddings.

**Install:**

```sh
chmod +x install.sh
./install.sh
```

The installer is interactive and does everything: unzips the bundle into an
install directory, asks how to run Compendium — **host-native (uv)**, which also
installs the four always-on launchd/systemd services (backup, curation schedule,
inbox watcher, access surface), or **Docker app image** for a headless LAN
server — provisions the backing stores with Docker, prompts for the
configuration (endpoints, API keys, paths, bind address) to generate `.env`,
applies migrations, builds the derived indexes, and starts the services. The
access surface is then at `http://127.0.0.1:8787`.

Afterwards, drive the stack with `compendium start | stop | restart` (or
`deploy/compendiumctl`). Full instructions, the lock-it-down checklist, and the
update path are in the bundle's own `DEPLOY.md` and in
[`docs/operations/deployment.md`](docs/operations/deployment.md). The posture is
single-user, localhost/LAN, no auth, no TLS (ADR-011/012) — your host firewall
is the access control.

Installing from a git checkout instead? `deploy/install.sh` is the equivalent
one-shot deployer for the working tree.

## Requirements (development)

- macOS or Linux
- [uv](https://docs.astral.sh/uv/) — Python package manager
- Python 3.12 (uv installs it if missing)
- Docker — runs the local PostgreSQL instance

## Setup (development)

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
uv run pytest                  # full suite (needs the backing stores up)
uv run pytest -m "not golden"  # fast tier (what CI runs on push)
uv run pytest -m golden        # the golden quality suite (nightly tier)
uv run pytest -m live          # opt-in real-model tests (v0.2 Phase 1)
```

Tests use the deterministic stub embedder/synth (`COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1`) and skip integration tests when a store is unreachable. The golden dataset (`tests/golden/`) is the quality regression signal. CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the fast tier on every push/PR and the full golden suite nightly, with all four stores as service containers. The `live` tier exercises the real BGE-M3 and OpenRouter Claude seams against a live endpoint — opt-in only, never in CI; see [docs/operations/real-models.md](docs/operations/real-models.md) for the per-host model strategy and cost note.

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
  answer/          composed answers (`ask`)
  api/             access surface: facade + HTTP + MCP
  curate/          curation loop and edge extraction
  profiling.py     opt-in local profiler (spans, cProfile, tracemalloc)
  profile_stats.py read-only performance-stats aggregation
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

1. `docs/Compendium.md` — the complete design and build reference: product vision, architecture decisions (ADRs), data contracts, the original 11-phase build plan, and the testing strategy. Read it top to bottom if you are new.
2. `CLAUDE.md` — working context and architectural rules for AI coding sessions.
3. `openspec/changes/` — active change proposals, designs, specs, and task lists.
