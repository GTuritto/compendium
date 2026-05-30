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
| 0.2 | Missing required variable | Temporarily move `.env` aside (`mv .env .env.tmp`) so dotenv stops loading it; then `env -u POSTGRES_URL uv run python -m compendium`; restore with `mv .env.tmp .env`. | Non-zero exit code; error message names the missing variable; no Python traceback. |
| 0.3 | Validation does no I/O | Move `.env` aside and run with a minimal env that points every storage URL at a closed port (e.g. `POSTGRES_URL=postgresql://x:x@127.0.0.1:1/x ...`); restore `.env` afterwards. | Still exits 0 — config validation only resolves and parses values, it never connects. |
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

Prerequisites: Phase 3's ingest fixtures available; the stub embedder is fine
(`export COMPENDIUM_EMBED_STUB=1`) so no embeddings endpoint is needed.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 4.1 | Stores up | `docker compose up -d opensearch qdrant` | Both reachable: `curl :9200` and `curl :6533/collections` respond (Qdrant's host port is remapped to 6533 in `docker-compose.yml`). |
| 4.2 | Schemas created | `uv run python -m compendium reindex all` (empty corpus is fine) | The `pages`/`chunks` indexes and collections exist; command exits 0. |
| 4.3 | Populate | Ingest `sample.md` and `sample.pdf`, then `uv run python -m compendium index sync` | `index status` shows pending 0 and indexed counts equal to the page and chunk totals. |
| 4.4 | OpenSearch query | `curl 'http://localhost:9200/pages/_search?q=body:psychological'` | A relevant page appears in the hits. |
| 4.5 | Qdrant query | `qdrant-client.query_points(collection_name='pages', query=embed('psychological safety'), limit=3)` (the `search` method is deprecated in qdrant-client ≥ 1.10) | A relevant page point is returned. |
| 4.6 | Deterministic rebuild | Drop the indexes, `uv run python -m compendium reindex all` | Counts are restored; the 4.4 query returns the same top page (Qdrant top-K within a small Jaccard distance). |

## Phase 5 — Page-first retrieval

Prerequisites: Phase 4's stores up (`docker compose up -d opensearch qdrant`),
a migrated database, and Phase 3's `sample.md` ingested with its source page
indexed (`uv run python -m compendium ingest tests/fixtures/sample.md --kind note`
then `uv run python -m compendium reindex all`). The stub embedder is fine
(`export COMPENDIUM_EMBED_STUB=1`).

The coverage values below assume this minimal corpus (only `sample.md` indexed,
so a single source page). Coverage is the normalized top-k mean, so it is
corpus-dependent: with more pages indexed the page list is longer and coverage
is lower than 1.000. Run from a clean vault + `reindex all` to reproduce the
single-source numbers, or read the values as "high, no fallback" on a larger
corpus.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 5.1 | Covered query returns pages | `uv run python -m compendium query "psychological safety team learning"` | Exit 0; on stdout, a `query:` summary line reporting a high coverage and no fallback (`coverage 1.000` on the single-source corpus; lower but still no-fallback on a larger one), then the `Sample Markdown Source` page listed with a score. |
| 5.2 | JSON output | `uv run python -m compendium query "psychological safety" --format json` | Exit 0; a JSON object with `query`, `coverage_score`, `fallback_to_chunks`, a non-empty `pages` array, `citations`, and `gaps`. (`--format json` replaces the former `--json`; available on every read command.) |
| 5.3 | Gap → chunk fallback | Drop both `pages` indexes and recreate them empty: `curl -X DELETE 'http://localhost:9200/pages'`, then call `compendium.index.opensearch.ensure_indexes(opensearch_client())` (or `compendium reindex all` on an empty corpus) to recreate the OpenSearch `pages` index empty, then `qdrant_client.delete_collection('pages')` + `create_collection('pages', vectors_config=VectorParams(size=1024, distance=Distance.COSINE))`. Then `uv run python -m compendium query "psychological safety team learning"`. | Exit 0; no pages, chunk citations from `Sample Markdown Source` are shown under "citations (chunk fallback)". |
| 5.4 | Traces persisted | `PSQL "SELECT query_text, round(coverage_score::numeric,3), fallback_to_chunks, jsonb_array_length(gaps), array_length(query_embedding,1), graph_expansion FROM query_traces ORDER BY created_at"` | One row per query above: the covered queries show a high coverage (`1.000` on the single-source corpus), fallback `f`, 0 gaps; the 5.3 query shows coverage `0.000`, fallback `t`, 1 gap; every row has `query_embedding` length 1024 and `graph_expansion` NULL. |

## Phase 6 — Memgraph structural index

Prerequisites: Memgraph up (`docker compose up -d memgraph`, reachable on
`bolt://localhost:7688`), a migrated database, and Phase 3's `sample.md`
ingested with a synthesized `concept` page (`COMPENDIUM_SYNTH_STUB=1 uv run
python -m compendium synth concept "psychological safety"`).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 6.1 | Memgraph up | `docker compose up -d memgraph` | reachable on `bolt://localhost:7688`. |
| 6.2 | Rebuild | `uv run python -m compendium graph rebuild` | Exit 0; reports node counts (`Source`, `Concept`, `Chunk`) and edge counts (`PART_OF`, `EVIDENCES`, `GROUNDS`) matching the corpus. |
| 6.3 | Status | `uv run python -m compendium graph status` | per-label node counts and per-type edge counts; only `PART_OF`/`EVIDENCES`/`GROUNDS` are non-zero (the four semantic edges are defined but unpopulated in v0.1). |
| 6.4 | Acceptance traversal | Cypher (e.g. via `mgconsole` or the driver) `MATCH (s:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(c:Concept) RETURN DISTINCT s.title, c.title` | returns the seeded source/concept pair(s), e.g. `Sample Markdown Source` / `psychological safety`. |
| 6.5 | Sync after write | re-ingest a fixture, then `uv run python -m compendium index sync` | the entity's node and automatic edges appear in the graph; `v_sync_lag` shows the `memgraph` kind drained to `indexed`. |
| 6.6 | Unreachable handling | stop Memgraph, `uv run python -m compendium graph status` | prints `memgraph: unreachable` and exits 1 (no traceback). |

## Phase 7 — Query traces and revision tracking

Prerequisites: the stack up, a migrated database, Phase 3's `sample.md` ingested
with a synthesized `concept` page and the indexes populated (so a query can run),
and at least one query made (`COMPENDIUM_EMBED_STUB=1 uv run python -m compendium
query "psychological safety team learning"`).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 7.1 | Trace list/show | `uv run python -m compendium trace list`, then `trace show <id>` | the query's trace is listed with coverage/fallback/gaps; `show` renders its pipeline, final ranking, latencies, coverage, and gaps. |
| 7.2 | Replay (read-only) | `uv run python -m compendium trace replay <id>` | prints the original-vs-current ranking diff and the coverage delta; the `query_traces` row count is unchanged. |
| 7.3 | Replay persists | `uv run python -m compendium trace replay <id> --persist` | a new `query_traces` row is written for the replay. |
| 7.4 | Revision diff | `uv run python -m compendium page revisions psychological-safety`, then `page diff psychological-safety 1 2` | revisions listed with ordinal/id/generator; the diff shows the body delta and the frontmatter key-delta. |
| 7.5 | Promote + list | `uv run python -m compendium page promote psychological-safety --to canonical`, then `promotions list` | the page's status becomes `canonical`; a `draft_to_canonical` event is listed with its timestamp. Re-promoting a canonical page is rejected. |

## Phase 8 — TUI ops console

Prerequisites: the full stack up and a seeded corpus (ingest a fixture, synth a
concept, `reindex all`, `graph rebuild`). Launch in a real terminal. Navigation
is keyboard-only: `d` dashboard, `s` sources, `p` pages, `w` workbench,
`c` curation, `g` graph, `?` help, `q` quit. On the workbench and graph screens,
press `/` to focus the search box (so the nav letters are not typed into it).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 8.1 | Launch + navigate | `uv run python -m compendium tui`, press `d`/`s`/`p`/`w`/`c`/`g`, then `?` | each screen renders; the footer lists the bindings; `?` shows the help modal; no mouse used. |
| 8.2 | Dashboard | open dashboard, press `r` | table counts, sync-lag rows, and recent traces render. |
| 8.3 | Ingest a source | sources (`s`) → `i` → enter `tests/fixtures/sample.md`, kind `note` → Enter | the source appears with its inspection status after the worker completes. |
| 8.4 | Run a synth | pages (`p`) → `y` → kind `concept`, name `psychological safety` (`COMPENDIUM_SYNTH_STUB=1`) → Enter | the concept page appears in the list. |
| 8.5 | Workbench query | workbench (`w`) → `/` → type `psychological safety` → Enter | ranked pages + coverage render; a new trace appears on the dashboard. |
| 8.6 | Browse the graph | graph (`g`) → `/` → type `Sample` → Enter → select a node row → Enter | matching nodes list; walking the selection renders the reachable nodes and typed edges. |
| 8.7 | Quit | press `q` | the app exits cleanly to the shell. |

## Phase 9 — Knowledge graph curation loop

Prerequisites: the full stack up, a migrated database, `sample.md` ingested,
`reindex all` + `graph rebuild` done. Stub embedder/synth are fine
(`export COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1`). The loop is the
acceptance: a gap → a signal → a synth'd draft → promotion → an improved replay.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 9.1 | Create a gap | empty the pages indexes (`curl -X DELETE :9200/pages`; recreate the empty `pages` Qdrant collection), `uv run python -m compendium query "psychological safety"`, then `reindex all` | a coverage-0 / fallback trace is recorded for the query |
| 9.2 | Slow loop | `uv run python -m compendium curate run` | a `graph_analysis_runs` row; new open signal(s) including a `low_coverage_query` for the query |
| 9.3 | List signals | `uv run python -m compendium curate list` | open signals by priority with kind + summary |
| 9.4 | Synth from signal | `uv run python -m compendium curate synth <signal-id>` | a draft concept page that lint-passes and cites chunks; the signal moves to `in_progress` |
| 9.5 | Promote closes the loop | `uv run python -m compendium page promote <slug> --to canonical`, then `reindex all` | the signal becomes `addressed` with `addressed_revision_id`; a `SYNTHESIZES` edge is added (`graph status` shows it) |
| 9.6 | Replay improved | `uv run python -m compendium trace replay <gap-trace-id>` | the replay shows the new page added and a positive coverage delta vs the original gap |
| 9.7 | Fast-loop expansion | `uv run python -m compendium graph link <a-slug> <b-slug> --type RELATED_TO`, then `query` a term hitting page a, then `compendium trace show <trace-id>` (or inspect `query_traces.graph_expansion` directly) | the trace's `graph_expansion` is populated (`reached` lists page b with a `hop`/`score`); page b is merged into the final ranking. Note: `query --format json` does not currently include `graph_expansion` in its output; use `trace show` or the DB column for verification. |
| 9.8 | Curator in the TUI | `compendium tui` → `c` → select a signal → `y` | the synth runs; the signal leaves the open queue (moves to `in_progress`) |

## Phase 10 — Golden dataset and testing

Prerequisites: the full stack up. The golden suite is hermetic (stub embedder) —
`export COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1`. It seeds its own
`compendium_golden` database and `.golden_vault`, and skips if a store is down.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 10.1 | Full suite | `COMPENDIUM_EMBED_STUB=1 uv run pytest` | the whole suite passes (unit + integration + pipeline + graph + golden) |
| 10.2 | Golden only | `COMPENDIUM_EMBED_STUB=1 uv run pytest -m golden` | the golden dataset (categories A/C/D) passes on the baseline |
| 10.3 | Fast tier | `COMPENDIUM_EMBED_STUB=1 uv run pytest -m "not golden"` | the fast tier passes, including the golden smoke; the golden full/regression tests are deselected |
| 10.4 | Regression trips | `COMPENDIUM_EMBED_STUB=1 uv run pytest tests/test_golden.py::test_regression_detector` | passes — i.e. with the ranker (RRF) deliberately disabled, a golden assertion fails and the detector catches it |
| 10.5 | CI workflow | inspect `.github/workflows/ci.yml` (or `act -n`) | a `test` job (push/PR) and a `nightly` job (schedule), each declaring Postgres/OpenSearch/Qdrant/Memgraph service containers with the stub embedder |

## Phase 1 (v0.2) — Real-model validation

Opt-in walk that exercises the real model seams (`OpenAIEmbedder` →
`https://openrouter.ai/api/v1`, `LLMSynthesizer` → same endpoint) on the
primary host. Default `.env` and stub flags unset; see
[../docs/operations/real-models.md](../docs/operations/real-models.md) for
the per-host strategy and cost note. Captured runs land under
[test-runs/](test-runs/) (`v0.2-phase-1-real-models.md`).

Prerequisite: `unset COMPENDIUM_EMBED_STUB COMPENDIUM_SYNTH_STUB`; `.env`
populated per `docs/operations/real-models.md`; `docker compose up -d`.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-1.1 | Live tests pass | `uv run pytest -m live` | both `test_real_embedder_roundtrip` and `test_real_synthesizer_writes_prose` PASS in under 15 s |
| v0.2-1.2 | Qdrant point is real | after `uv run python -m compendium reindex all`, pull one point from the `chunks` Qdrant collection with vectors enabled | vector length 1024; L2 norm within 1e-3 of 1.0; the vector does not equal `StubEmbedder()._vector(body)` for the same chunk body |
| v0.2-1.3 | Real synth output | `uv run python -m compendium synth concept "<name appearing in the corpus>"` | a vault page is written whose body starts with `# `, is at least 200 chars, and does not contain `stub synthesizer` |
| v0.2-1.4 | Focused real-model walk | reindex (Phase 4) → query (Phase 5) → synth (Phase 3) → graph rebuild (Phase 6) → curate run (Phase 9) → trace inspection (Phase 7), all with stubs unset | every step exits 0; query coverage > 0.5 with no fallback for a corpus-covered query; synth wall-clock per concept < 30 s; capture into `test-runs/v0.2-phase-1-real-models.md` |
| v0.2-1.5 | Hermetic suite still green | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run pytest` | 86 passed, 2 deselected (the two live tests, correctly) |
