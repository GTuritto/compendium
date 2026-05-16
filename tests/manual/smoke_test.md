# Compendium — Manual Smoke-Test Playbook

A cumulative, end-to-end manual test walk. It grows one section per phase as the
build progresses. After a phase merges, its smoke-test section is final; the full
walk from Phase 0 onward should still pass on every later phase.

## How to use this file

- Run from the repository root with the dev environment up (`docker compose up -d`).
- Commands are copy-paste-ready. Python entrypoints are prefixed with `uv run`.
- Paths are relative to the repo root.
- A scenario passes only if the actual result matches the **Expected** column
  exactly (output, exit code, and any database/index state described).
- Each phase's section is authored in that phase's Phase Plan
  (`Plans/phase-N-<name>.md`) and appended here as part of the phase.

Scenarios are numbered `N.M` — phase `N`, scenario `M`.

## Phase 0 — Project skeleton

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 0.1 | Cold start | `cp .env.example .env` and fill values; `uv run python -m compendium` | Prints `Compendium starting` and the resolved storage URLs (`POSTGRES_URL`, `OPENSEARCH_URL`, `QDRANT_URL`, `MEMGRAPH_URL`). Exit code 0. |
| 0.2 | Missing required variable | Unset a required var (e.g. `POSTGRES_URL`); `uv run python -m compendium` | Non-zero exit code; error message names the missing variable; no Python traceback. |
| 0.3 | Validation does no I/O | With all storage backends stopped (`docker compose down`), `uv run python -m compendium` | Still exits 0 — config validation only resolves and parses values, it never connects. |
| 0.4 | Log structure | `uv run python -m compendium 2>&1 1>/dev/null \| jq .` | Each line is valid JSON with `event`, `level`, and an ISO-8601 `ts`. No secret values (API keys) appear in the output. |

## Phase 1 — PostgreSQL operational backbone

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 1.1 | Dev database up | `docker compose up -d`; wait for healthy | The `postgres:16` container is running and accepts connections on `localhost:5432`. |
| 1.2 | Upgrade builds full schema | From an empty database, `uv run alembic upgrade head` | Completes without error. All operational tables, the ten enum types, and the four `v_*` views exist. |
| 1.3 | Downgrade reverses cleanly | `uv run alembic downgrade base` | Completes without error; every table, enum, and view created by the migrations is gone, leaving an empty schema. |
| 1.4 | Stub round-trip | `uv run alembic upgrade head`; insert a stub `source` and a stub `wiki_page` through `compendium/db/`, then read them back | The read rows match what was inserted, including JSONB, array, and enum-typed columns. |
| 1.5 | Operational views queryable | After `upgrade head`, select from `v_sync_lag`, `v_failed_sources`, `v_recent_traces`, and `v_open_curation_signals` | Each query succeeds and returns the documented columns (empty result sets are fine). |

## Phase 2 — Ingestion pipeline

Run with the dev database migrated (`uv run alembic upgrade head`). Counts
assume a freshly migrated, empty database.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 2.1 | Ingest a PDF | `uv run python -m compendium ingest tests/fixtures/sample.pdf --kind paper` | Reports `1 stored`; one `sources` row and one or more `chunks`. |
| 2.2 | Ingest EPUB and HTML | `uv run python -m compendium ingest tests/fixtures/sample.epub --kind book` then `... ingest tests/fixtures/sample.html --kind web` | Two more sources; each reports `1 stored` with chunks. |
| 2.3 | Re-ingest is idempotent | `uv run python -m compendium ingest tests/fixtures/sample.pdf --kind paper` | Reports `1 unchanged`; `sources` and `chunks` counts do not change. |
| 2.4 | Failed source | `uv run python -m compendium ingest tests/fixtures/broken.pdf --kind paper` | Reports `1 failed`; the source has `inspection_status = failed` and appears in `v_failed_sources` with a reason. |
| 2.5 | Authored provenance | `uv run python -m compendium ingest tests/fixtures/sample.md --kind note --mine` | `1 stored`; that source's `metadata` has `authored_by_me: true`. |
| 2.6 | Directory ingest | `uv run python -m compendium ingest tests/fixtures/` | Every file in the directory is handled as its own source; run after 2.1–2.5, all five report `unchanged` (their content hashes are already stored). |

## Phase 3 — Wiki page generation and canonical frontmatter

Run with the dev database migrated and a clean vault
(`find vault -name '*.md' -delete`).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 3.1 | Source page on ingest | `uv run python -m compendium ingest tests/fixtures/sample.pdf --kind paper` | A `source` page appears in `vault/sources/`. |
| 3.2 | Backfill source pages | Ingest `sample.epub` and `sample.md`, then `uv run python -m compendium pages build` | A `source` page exists for every ingested source (`pages build` reports `0` since the ingest hook already made them). |
| 3.3 | Lint a clean vault | `uv run python -m compendium lint` | Reports zero errors; exit 0. |
| 3.4 | Lint catches a bad page | Hand-edit a page to break the slug or drop a required field; `uv run python -m compendium lint` | The failing rule is reported as an error; exit 1. |
| 3.5 | Concept synthesis | `COMPENDIUM_SYNTH_STUB=1 uv run python -m compendium synth concept "psychological safety"` | A `concept` page is written, passes lint, and its `## Grounding` section cites at least two chunks across at least two sources. |
| 3.6 | Revision recorded | After 3.5, `PSQL "SELECT kind, generator FROM wiki_page_revisions JOIN wiki_pages ON wiki_pages.id = wiki_page_revisions.page_id"` | A revision row exists for the concept page with `generator = synth`. |

## Phase 4 — Derived indexes (OpenSearch + Qdrant)

_Smoke-test scenarios authored in `Plans/phase-4-derived-indexes.md` and appended here when Phase 4 is implemented._

## Phase 5 — Page-first retrieval

_Smoke-test scenarios authored in `Plans/phase-5-retrieval.md` and appended here when Phase 5 is implemented._

## Phase 6 — Memgraph structural index

_Smoke-test scenarios authored in `Plans/phase-6-memgraph.md` and appended here when Phase 6 is implemented._

## Phase 7 — Query traces and revision tracking

_Smoke-test scenarios authored in `Plans/phase-7-traces.md` and appended here when Phase 7 is implemented._

## Phase 8 — TUI ops console

_Smoke-test scenarios authored in `Plans/phase-8-tui.md` and appended here when Phase 8 is implemented._

## Phase 9 — Knowledge graph curation loop

_Smoke-test scenarios authored in `Plans/phase-9-curation-loop.md` and appended here when Phase 9 is implemented._

## Phase 10 — Golden dataset and testing

_Smoke-test scenarios authored in `Plans/phase-10-testing.md` and appended here when Phase 10 is implemented._
