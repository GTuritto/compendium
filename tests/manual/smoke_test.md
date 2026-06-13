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

**CI automation:** the CI-runnable layers of this playbook are scripted in
[`deploy/ci-smoke.sh`](../../deploy/ci-smoke.sh) and run as the `smoke` job in
`.github/workflows/ci.yml` on every `main` push and `v*` tag; the distribution
bundle is built only when that gate is green. Host-bound scenarios
(launchd/systemd unit installs, the interactive TUI walk, the live real-model
tier, the restore round-trip) remain manual — this playbook stays the source of
truth for the full walk.

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

> Non-interactive equivalent: the TUI is a full-screen interactive Textual app,
> so 8.1–8.7 cannot be driven from a non-TTY shell (CI or an agent). The headless
> equivalent is the Textual **Pilot** suite — `COMPENDIUM_EMBED_STUB=1
> COMPENDIUM_SYNTH_STUB=1 uv run pytest tests/test_tui.py` — which boots the app,
> reaches all six screens + the help modal, and drives the keyboard ingest →
> synth → workbench-query → graph-browse session. Run that to verify the TUI
> without a terminal; the manual walk below is for a human at a real terminal.

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
| v0.2-1.5 | Hermetic suite still green | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run pytest` | the full suite passes; only the two `live` tests are deselected, no failures (as of v0.2 Phase 7: 209 passed, 1 skipped, 2 deselected — the absolute count grows each phase) |

## Phase 2 (v0.2) — Backup / restore

Opt-in walk that exercises the new `compendium backup` and
`compendium restore` CLI verbs and the per-OS scheduled unit. The
operational reference is
[../docs/operations/backup-restore.md](../docs/operations/backup-restore.md).

Prerequisites: `pg_dump` / `pg_restore` / `tar` on PATH (macOS:
`brew install libpq && brew link --force libpq`); a populated
PostgreSQL + vault (run the v0.1 Phase 2 / 3 smoke first); `.env`
populated.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-2.1 | Local backup writes the pair | `BACKUP_LOCAL_DIR=./backups BACKUP_RSYNC_DEST= uv run python -m compendium backup` | a new directory `backups/<UTC-timestamp>/` contains `compendium.dump` (non-empty) and `vault.tar.gz` (non-empty); exit 0 |
| v0.2-2.2 | rsync mirror to off-host | re-run with `BACKUP_RSYNC_DEST=/tmp/cdb-test/` exported | after success, `/tmp/cdb-test/<same-timestamp>/` contains the same two files; exit 0 |
| v0.2-2.3 | rsync failure isolation | re-run with `BACKUP_RSYNC_DEST=user@no.such.host:/x` | the local backup pair is written; the command exits non-zero with `backup rsync failed`; the local backup is retained and valid |
| v0.2-2.4 | Restore returns the system | drop the live database (`docker compose exec postgres dropdb -U compendium compendium && createdb -U compendium compendium`) and wipe the vault (`find vault -name '*.md' -delete`); then `uv run python -m compendium restore <timestamp> --force` | `pg_restore` runs clean; the vault is repopulated; stdout includes `Run 'compendium reindex all' and 'compendium graph rebuild' to repopulate the derived stores.`; exit 0 |
| v0.2-2.5 | Same answers after rebuild | `uv run python -m compendium reindex all && uv run python -m compendium graph rebuild`, then `uv run python -m compendium query "psychological safety team learning"` | coverage and top-page identical (within RRF-tie tolerance) to the same query run before the backup |
| v0.2-2.6 | Schedule install + uninstall | `uv run python -m compendium backup install --at 03:15` | on macOS: `~/Library/LaunchAgents/com.compendium.backup.plist` exists with `Hour=3, Minute=15`; `launchctl print gui/<uid>/com.compendium.backup` succeeds. `uv run python -m compendium backup uninstall` removes the plist; re-running uninstall exits 0 with "not installed". |

## Phase 3 (v0.2) — Scheduled curation daemon

Opt-in walk that exercises the new `compendium schedule
install/uninstall/status` verbs and confirms a kicked fire produces
a `graph_analysis_runs` row. The operational reference is
[../docs/operations/schedule.md](../docs/operations/schedule.md).

Prerequisites: the v0.1 Phase 2 + Phase 4 corpus seeded (so curate
has something to look at); `.env` populated; stores up.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-3.1 | Install at default cadence | `uv run python -m compendium schedule install` | macOS: `~/Library/LaunchAgents/com.compendium.curate.plist` exists with `StartInterval=3600`; `launchctl print gui/<uid>/com.compendium.curate` succeeds. Linux: `~/.config/systemd/user/compendium-curate.timer` carries `OnUnitActiveSec=3600`; `systemctl --user is-enabled compendium-curate.timer` reports `enabled`. Exit 0. |
| v0.2-3.2 | Install at a custom cadence | `uv run python -m compendium schedule uninstall && uv run python -m compendium schedule install --every 30m` | unit's interval is 1800 seconds (macOS `StartInterval=1800`; Linux `OnUnitActiveSec=1800`). Exit 0. |
| v0.2-3.3 | Status of a loaded unit | `uv run python -m compendium schedule status` | text block: `loaded=True`, `state="not running"` (or `active` on Linux), `interval` matches the install, `last_fired="(never exited)"` (or `(unknown)`) before any fire, `next_fire="(unknown)"` on macOS / populated wall-clock on Linux. Exit 0. |
| v0.2-3.4 | Manual kick produces a `graph_analysis_runs` row | `psql -c "SELECT count(*) FROM graph_analysis_runs"` (record pre); `launchctl kickstart -k gui/$(id -u)/com.compendium.curate` (macOS) or `systemctl --user start compendium-curate.service` (Linux); wait up to 30 s; re-check the count | post-count = pre-count + 1; the new row has a populated `inserted` / `by_kind` summary. |
| v0.2-3.5 | Status after a fire shows `last_fired` | re-run `compendium schedule status` after v0.2-3.4 | macOS: `last_fired` becomes a populated exit-code field (typically `0`); Linux: `last_fired` becomes a wall-clock timestamp inside the last minute. Exit 0. |
| v0.2-3.6 | Uninstall + idempotent uninstall | `uv run python -m compendium schedule uninstall` then again | first call removes the unit and exits 0; second call exits 0 with "not installed"; `compendium schedule status` after uninstall exits 1 with `state="absent"`. |

## Phase 4 (v0.2) — Ingestion automation (inbox)

Opt-in walk that exercises `compendium inbox install` / `process` /
`status` / `uninstall`. The operational reference is
[../docs/operations/inbox.md](../docs/operations/inbox.md).

Prerequisites: stores up; `.env` populated. The walk uses a
tmp inbox at `/tmp/cdb-inbox-smoke` so it does not collide with the
operator's real `~/Compendium/inbox`. The corrupt-file scenario uses
a unique-content fixture each run so the content hash never collides
with a previously-failed `broken.pdf`.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-4.1 | Install creates the layout | `rm -rf /tmp/cdb-inbox-smoke && uv run python -m compendium inbox install --path /tmp/cdb-inbox-smoke` | `/tmp/cdb-inbox-smoke/{book,article,paper,note,web,processed,failed}/` exist; on macOS `~/Library/LaunchAgents/com.compendium.inbox.plist` exists; on Linux `~/.config/systemd/user/compendium-inbox.{path,service}` exist; exit 0 |
| v0.2-4.2 | Drop a good PDF | `cp tests/fixtures/sample.pdf /tmp/cdb-inbox-smoke/paper/` then `uv run python -m compendium inbox process --path /tmp/cdb-inbox-smoke` | the file is now under `/tmp/cdb-inbox-smoke/processed/$(date -u +%Y-%m-%d)/sample.pdf`; one new row in `sources`; summary reports `processed=1 failed=0 skipped=0`; exit 0 |
| v0.2-4.3 | Drop a unique corrupt PDF | `echo "NOT-A-PDF-$(date +%s%N)" > /tmp/cdb-inbox-smoke/paper/garbage-$(date +%s).pdf` then `uv run python -m compendium inbox process --path /tmp/cdb-inbox-smoke` | the file is now under `/tmp/cdb-inbox-smoke/failed/$(date -u +%Y-%m-%d)/garbage-*.pdf`; a sidecar `garbage-*.pdf.error` exists in the same directory containing the parser's reason ("could not open PDF: ..."); summary reports `processed=0 failed=1 skipped=0`; exit 0 |
| v0.2-4.4 | Status reports the counts | `uv run python -m compendium inbox status --path /tmp/cdb-inbox-smoke` | text block shows `watcher_loaded=True, processed today=1, failed today=1`, `most_recent_processed` and `most_recent_failed` populated. `--format json` emits the same as a JSON object. Exit 0. |
| v0.2-4.5 | Skip-filter ignores `.crdownload` | `cp tests/fixtures/sample.pdf /tmp/cdb-inbox-smoke/paper/x.pdf.crdownload` then `compendium inbox process --path /tmp/cdb-inbox-smoke` | the `.crdownload` file remains under `paper/`; no new `sources` row; the summary reports `skipped=1` |
| v0.2-4.6 | Uninstall + idempotent uninstall | `uv run python -m compendium inbox uninstall` then again; then `uv run python -m compendium inbox status --path /tmp/cdb-inbox-smoke` | first uninstall removes the watcher unit and exits 0; second exits 0 with "not installed"; status reports `watcher_loaded=False` but still shows the file counts (the inbox directory and contents are preserved); exit 0 |

## Phase 5 (v0.2) — Retrieval tuning

Opt-in walk that exercises `tests/golden/baseline.json`, the
`--golden-baseline` regeneration flag, the rule-based query
normalizer, and the OpenSearch synonym filter + Qdrant HNSW
parameters. The operational reference is
[../docs/operations/retrieval-tuning.md](../docs/operations/retrieval-tuning.md).

Prerequisites: stores up; `.env` populated; the golden corpus
fixture (the test seeds it under `compendium_golden` on first
invocation).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-5.1 | Baseline regenerates cleanly | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run pytest -m golden --golden-baseline -q` | `tests/golden/baseline.json` is rewritten with the current per-query and aggregated metrics; the golden suite passes (no comparison gate) |
| v0.2-5.2 | Default golden run compares + prints deltas | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run pytest -m golden -q` | the suite passes; `test_golden_baseline` prints any drift > `0.01` absolute to stdout informationally (not gated in v0.2 Phase 5) |
| v0.2-5.3 | Existing per-query gate still holds | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run pytest tests/test_golden.py::test_golden_dataset -m golden -q` | passes — every query's `must_include_slug` is in its `top_k` |
| v0.2-5.4 | Query normalization end-to-end | `uv run python -m compendium query "The Psychological Safety concept"` | the latest `query_traces` row has `query_text="The Psychological Safety concept"` (raw) and `pipeline->>'normalized_query'='psychological safety concept'` (lowercased + stop-words stripped); the canonical concept page is at top-K |
| v0.2-5.5 | Alias expansion via synonym filter | `uv run python -m compendium query "psych safety"` (against a corpus where the `psychological-safety` concept carries the `psych safety` alias) | the canonical concept page returns at top-K; the OpenSearch query against `body:psych safety` returns the page even though the body never literally contains `"psych safety"` (the synonym filter expanded it at index time) |
| v0.2-5.6 | Tuning loop end-to-end | follow `docs/operations/retrieval-tuning.md` § "The tuning loop" — capture before, change one knob, reindex, capture after, diff | the diff shows the new baseline; per-query `test_golden_dataset` still passes; aggregate metric movement is the operator's directional signal |

## Phase 6 (v0.2) — Composed answers (`ask`)

Opt-in walk that exercises `compendium ask`: a covered question (answer with
citations), an uncovered question (refusal with suggested actions), and the
`ask_traces` row joined to `query_traces`. The operational reference is
[../docs/operations/ask.md](../docs/operations/ask.md).

Prerequisites: stores up; `.env` populated; a populated wiki (run the earlier
phases' seeding or ingest a source + synth a concept first). The LLM uses the
`SYNTHESIS_*` config; set `COMPENDIUM_SYNTH_STUB=1` to walk it deterministically
with no network or cost (answers are stub text, but the structure, refusal, and
traces are real).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-6.1 | Covered question answered + streamed | `uv run python -m compendium ask "<a question the corpus covers>"` | the composed answer streams to stdout token by token, then a `citations:` block (each `[n] Title (slug)  trace_rank=n`) and a footer (`coverage …  trace …  ask_trace …`); exit 0 |
| v0.2-6.2 | Uncovered question refused | `uv run python -m compendium ask "an utterly unrelated question about nothing in the corpus"` | `refused`, no answer, a `gap:` line, and `suggested actions:` naming the next CLI command (`compendium ingest …` when nothing covers it, else `compendium synth concept "…"`); exit 0 |
| v0.2-6.3 | `ask_traces` row joined to `query_traces` | after v0.2-6.1: `psql "$POSTGRES_URL" -c "SELECT a.prompt_template_id, a.model, a.input_tokens, a.output_tokens, a.cost_estimate, a.refused, q.query_text FROM ask_traces a JOIN query_traces q ON q.id = a.query_trace_id ORDER BY a.created_at DESC LIMIT 1;"` | one row: `prompt_template_id=ask-v1`, the model + token counts + a cost estimate, `refused=f`, and the joined `query_text` (the rewritten retrieval query) |
| v0.2-6.4 | JSON contract | `uv run python -m compendium ask "<a covered question>" --format json` | stdout is exactly one JSON object with `answer`, `refused`, `citations` (each `{ref, slug, title, trace_rank}`), `coverage_score`, `trace_id`, `ask_trace_id`, `gap`, `suggested_actions` |
| v0.2-6.5 | Refusal also writes an ask trace | after v0.2-6.2: `psql "$POSTGRES_URL" -c "SELECT refused, answer_text FROM ask_traces ORDER BY created_at DESC LIMIT 1;"` | one row with `refused=t` and a null `answer_text` |

## Phase 7 (v0.2) — Access surface (MCP + HTTP)

Opt-in walk that exercises `compendium serve` (HTTP on `127.0.0.1`) and
`compendium mcp` (stdio). The operational reference is
[../docs/operations/access-surface.md](../docs/operations/access-surface.md).

Prerequisites: stores up; `.env` populated; a populated wiki (run the earlier
phases' seeding or ingest a source first). The LLM uses the `SYNTHESIS_*`
config; set `COMPENDIUM_SYNTH_STUB=1` (and `COMPENDIUM_EMBED_STUB=1` if you
seeded with stub embeddings) to walk it deterministically with no network cost.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-7.1 | Start the HTTP server | `uv run python -m compendium serve &` then `curl -s 127.0.0.1:8787/index_status` | JSON `IndexStatusReport` (opensearch/qdrant counts + sync-lag); server bound to `127.0.0.1` |
| v0.2-7.2 | `query` over HTTP | `curl -s -XPOST 127.0.0.1:8787/query -H 'content-type: application/json' -d '{"text":"psychological safety"}'` | JSON `RetrievalResult` — ranked `pages`, `coverage_score`, `trace_id` |
| v0.2-7.3 | `ingest` raw bytes auto-syncs | `curl -s -XPOST 127.0.0.1:8787/ingest -H 'content-type: application/json' -d "{\"kind\":\"note\",\"filename\":\"sr.md\",\"content_base64\":\"$(printf '# Spaced Repetition\n\nSpaced repetition schedules reviews at increasing intervals.' | base64)\"}"` then repeat v0.2-7.2 for "spaced repetition intervals" | `IngestResult` (status + source_id + chunk_count); the follow-up `query` finds the new source without a manual reindex (the surface ran `index sync`) |
| v0.2-7.4 | `ask` over HTTP (covered + refusal) | `curl -s -XPOST 127.0.0.1:8787/ask -H 'content-type: application/json' -d '{"question":"What is psychological safety?"}'` then an off-topic question | covered → `answer` + `citations[]` (`[1] {ref,slug,title,trace_rank}`) + `ask_trace_id`, `refused=false`; off-topic on a small corpus may still answer (coverage is structural) — raise `ask.refuse_below_coverage` to see `refused=true` + `suggested_actions` |
| v0.2-7.5 | `ask` streaming | `curl -sN -XPOST 127.0.0.1:8787/ask/stream -H 'content-type: application/json' -d '{"question":"What is psychological safety?"}'` | the answer text arrives in chunks, then a final JSON line with `citations`, `coverage_score`, `trace_id`, `ask_trace_id` |
| v0.2-7.6 | `page_list` / `page_get` | `curl -s '127.0.0.1:8787/page_list?kind=source'` then `curl -s '127.0.0.1:8787/page_get?kind=source&slug=<slug>'` | a filtered, newest-first page list; then frontmatter + body Markdown for the slug (404 for an unknown slug) |
| v0.2-7.7 | MCP from a client | point an MCP-aware client at the command `uv run python -m compendium mcp`; `list_tools`; invoke `query` and `ask` | six tools listed (`query, ask, ingest, page_get, page_list, index_status`); `query` returns ranked pages; `ask` returns a composed answer (tokens stream as log notifications) with citations |
| v0.2-7.8 | Loopback-only posture | from another host on the LAN, `curl --max-time 3 http://<this-host-ip>:8787/index_status` | connection refused / times out — the server bound `127.0.0.1` only (no auth, no exposure) |

Stop the server: `kill %1` (or the `serve` PID).

## Phase 8 (v0.2) — Autonomous semantic-edge extraction

Opt-in walk that exercises the `from_extracted_edges` generator inside
`compendium curate run`: it pulls Qdrant neighbours per changed page, labels
pairs with the LLM, and writes `RELATED_TO`/`PREREQUISITE_FOR` edges into
Memgraph with provenance. The operational reference is
[../docs/operations/edge-extraction.md](../docs/operations/edge-extraction.md).

Prerequisites: stores up; `.env` populated; a seeded corpus with at least two
concept/source pages and the indexes + graph built (`reindex all` +
`graph rebuild`). `COMPENDIUM_SYNTH_STUB=1` runs the deterministic stub labeller
(no network/cost); unset it to use the real model.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.2-8.1 | Cold-start extraction | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run python -m compendium curate run` (on a seeded corpus, before any LLM edges exist) | the run report's `extracted_edges.written >= 1`; `compendium graph status` now shows non-zero `RELATED_TO` and/or `PREREQUISITE_FOR` |
| v0.2-8.2 | Edges carry provenance | `psql`/`mgconsole` Cypher: `MATCH ()-[r:RELATED_TO {extracted_by:"llm"}]->() RETURN r LIMIT 3` | each edge has `model`, `confidence`, `extracted_at`, `source_revision_id`, and `weight` (= confidence) populated |
| v0.2-8.3 | Curator edge untouched | `compendium graph link <a-slug> <b-slug> --type RELATED_TO`; re-run `curate run`; inspect that edge | the edge keeps `extracted_by="curator"`; not overwritten; the run logs `dropped-by-collision` for that pair |
| v0.2-8.4 | Structural pre-filter | identify a `GROUNDS`-linked source/concept pair; re-run `curate run` | no LLM `RELATED_TO`/`PREREQUISITE_FOR` is written between that structurally-linked pair |
| v0.2-8.5 | Expansion finds new edges | `uv run python -m compendium query "<term hitting a page with a new LLM edge>"`, then `compendium trace show <trace-id>` (or inspect `query_traces.graph_expansion`) | the trace's `graph_expansion` reaches the linked neighbour via the new edge |
| v0.2-8.6 | Incremental run is quiet | re-run `curate run` with no corpus change (and not a full-sweep tick) | `extracted_edges.written == 0`; no duplicate edges created |
| v0.2-8.7 | Reversible by predicate | Cypher `MATCH ()-[r {extracted_by:"llm"}]-() WHERE r.confidence < 0.85 DELETE r` | only low-confidence LLM edges removed; curator edges and high-confidence LLM edges remain |

## Arch fix 1 — OS service-unit seam (behaviour-preserving)

Run on the primary host (macOS). Confirms the four services still install /
status / uninstall identically after consolidation behind `compendium/service_unit/`.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch1.1 | All four install with unchanged labels/paths | `compendium schedule install --every 1h`; `compendium backup install`; `compendium inbox install`; `compendium serve install` | plists at `~/Library/LaunchAgents/com.compendium.{curate,backup,inbox,serve}.plist` (Linux: units under `~/.config/systemd/user/`); all loaded |
| arch1.2 | Generated units unchanged | inspect each written plist / unit file | identical content to pre-fix (trigger keys, ProgramArguments, WorkingDirectory, log paths) |
| arch1.3 | Status reports unchanged | `compendium schedule status --format json`; `compendium inbox status --format json`; `compendium serve status --format json` | same JSON shape/values as before the fix |
| arch1.4 | Uninstall idempotent | run each `uninstall` twice | first removes; second is a no-op (`not installed`); inbox directory preserved |

## Arch fix 2 — EdgeType value object + provenance seam (behaviour-preserving)

Prerequisites: stores up; a seeded corpus with ≥2 pages and the graph built.
`COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1`. Confirms the consolidated edge
rules + the one provenance seam preserve ADR-009/010 behaviour.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch2.1 | Curator edge keeps orientation, still protected | `compendium graph link <a> <b> --type RELATED_TO`; inspect in Memgraph, then `curate run` | stored in the curator's orientation (a→b, not flipped) so expansion reaches b from a; a later extraction of the same pair is `dropped-by-collision` (the seam checks both directions). Canonicalisation is LLM-write-only. |
| arch2.2 | Curator edge survives extraction | after arch2.1, `compendium curate run`; inspect that edge | keeps `extracted_by="curator"`; the run logs `dropped-by-collision` for that pair; not overwritten |
| arch2.3 | Expansion walks the same set | query a term hitting a linked page, then `compendium trace show <id>` | `graph_expansion` walks `RELATED_TO`/`PREREQUISITE_FOR`/`SYNTHESIZES` only (CONTRADICTS excluded), as before |
| arch2.4 | CONTRADICTS still curator-only | `compendium graph link <a> <b> --type CONTRADICTS` | accepted (curator-set); never walked by expansion or written by the extractor |
| arch2.5 | Structural seam guard | (dev) `schema.upsert_edge(driver, "RELATED_TO", …)` | raises `ValueError` directing to `upsert_semantic_edge`; structural `PART_OF`/`EVIDENCES`/`GROUNDS` writes unaffected |

## Arch fix 3 — PageKind strategy registry (behaviour-preserving)

Prerequisites: stores up; migrated DB; clean-ish vault. `COMPENDIUM_EMBED_STUB=1
COMPENDIUM_SYNTH_STUB=1`. Confirms the consolidated per-kind rules preserve the
frontmatter contract, lint, and vault behaviour.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch3.1 | Frontmatter + subdirs unchanged | ingest a source; `synth concept "<term>"`; inspect `vault/concepts/*.md` + `vault/sources/*.md` | same frontmatter fields + order per kind; pages land in `concepts/` and `sources/` |
| arch3.2 | Lint clean | `compendium lint` on the seeded vault | 0 errors, exit 0 |
| arch3.3 | Per-kind lint still fires | hand-edit a source page to drop `source_id` (or a concept's `topic_ids` to a non-resolving id); `compendium lint` | the same per-kind rule fires (`kind-specific-fields` / `topic-ids-resolve`); exit 1 |
| arch3.4 | Rules live in one place | `grep -nE 'kind ==' compendium/wiki/{page,lint,vault}.py` | no per-kind *rule* branch remains; the only match is lint's cross-page topic-id lookup (context construction the topic rule consumes) |

## Arch fix 4 — SignalGenerator registry (behaviour-preserving)

Prerequisites: stores up; seeded corpus with a low-coverage gap. `COMPENDIUM_EMBED_STUB=1
COMPENDIUM_SYNTH_STUB=1`. Confirms the registry-driven slow loop produces the same signals.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch4.1 | Same signals + summary | seed a gap (empty pages, query, reindex), `compendium curate run` | same `by_kind` / `skipped` / `extracted_edges` summary as before; signals inserted with the same kinds/priorities |
| arch4.2 | Graph-down skip is kind-derived | stop Memgraph, `compendium curate run` | `skipped` lists exactly `thin_grounding`, `dangling_concept`, `unresolved_contradiction`; the low-coverage signal is still inserted; exit 0 |
| arch4.3 | Extractor still a separate step | `curate run` with stores up | `extracted_edges` counts are populated by the extraction step, which is absent from the SignalGenerator registry |
| arch4.4 | Rules in one place | `grep -nE 'graph_kinds|"thin_grounding"' compendium/curate/run.py` | no hardcoded kind-list; kinds + store-requirements live only in `signal_generator.py` / the registry |

## Arch — Semantic-edge persistence + replay (correctness fix, ADR-013)

Prerequisites: stores up; migrated DB (`alembic upgrade head` brings in `0013_semantic_edges`);
a seeded corpus with at least one concept + source. `COMPENDIUM_EMBED_STUB=1
COMPENDIUM_SYNTH_STUB=1`. Confirms a `graph rebuild` no longer wipes semantic edges.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-se.1 | Curator edge survives a rebuild | `compendium graph link <a> <b> --type RELATED_TO`; `compendium graph status`; `compendium graph rebuild`; `compendium graph status` | the `RELATED_TO` count is the same after the rebuild as before (was 0 before this fix) |
| arch-se.2 | SYNTHESIZES survives a rebuild | synth a concept from a signal and promote it (writes `SYNTHESIZES`); `compendium graph rebuild`; inspect | the `SYNTHESIZES` edge is present after the rebuild with `extracted_by="curator"` |
| arch-se.3 | LLM edge survives a rebuild | `compendium curate run` (writes `RELATED_TO`/`PREREQUISITE_FOR`); `compendium graph rebuild`; inspect one extracted edge | present after rebuild with `extracted_by="llm"` + confidence/model intact |
| arch-se.4 | Backfill captures legacy edges | on a graph with pre-fix in-graph-only edges: `compendium graph backfill-edges`; re-run it; `compendium graph rebuild` | first run reports a capture count; the second run reports the same count (idempotent — no duplicates); edges present after rebuild |
| arch-se.5 | Persistence is the source | after arch-se.1, `psql -c "SELECT edge_type, extracted_by FROM semantic_edges"` | a row exists for the curator edge with `extracted_by='curator'` |

## Arch — Cached config seam (behaviour-preserving)

Prerequisites: stores up; seeded corpus. `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1`.
Confirms the behavior-config readers resolve the same values, `serve` picks up a settings
change without restart, and storage-URL env overrides still take effect (uncached).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-cc.1 | Same behavior values | `compendium query "<term>"`; `compendium ask "<q>"`; `compendium curate run` | same ranked pages / refusal threshold / signals as before this fix |
| arch-cc.2 | serve picks up a settings change | start `compendium serve`; edit a non-secret value in `config/settings.yaml` (e.g. `ask.refuse_below_coverage`); hit `POST /ask` | the new value is in effect without restarting serve |
| arch-cc.3 | Env override still works (uncached) | `POSTGRES_URL=<other-db> compendium index status` | the other DB is used — storage-URL reads are not served from the behavior-config cache |
| arch-cc.4 | One home for keys/defaults | `grep -rn '\.settings\.get(' compendium/ \| grep -v config_sections.py` | no matches — `config_sections.py` (via its `_section` helper) is the only reader of the behavior sections; the inline extractors no longer dig the dict |

## Arch — Model client seam (behaviour-preserving)

Prerequisites: stores up; seeded corpus. Confirms the four model factories select through
one registry and a single `COMPENDIUM_LLM_STUB` runs every model seam offline (per-role flags
still work).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-lc.1 | One flag runs everything offline | `COMPENDIUM_LLM_STUB=1 uv run python -m compendium curate run` and `... ask "What is psychological safety?"` | both run with no network/cost — answerer/synthesizer/extractor/embedder all stubbed from the one flag |
| arch-lc.2 | Per-role flag still scoped | `COMPENDIUM_EMBED_STUB=1 uv run python -m compendium reindex all` (synth/answer flags unset) | only the embedder is stubbed; the synthesis-role clients would use real config |
| arch-lc.3 | Selection in one place | `grep -rln 'os.environ' compendium/answer/llm.py compendium/wiki/synth.py compendium/curate/extract.py compendium/index/embedder.py` | no matches — the four factories no longer read any env flag; the stub-vs-real decision lives only in `compendium/model_clients.py` (`get_model_client` / `use_stub`) |

## Arch — ask composition seam (behaviour-preserving)

Prerequisites: stores up; seeded corpus. `COMPENDIUM_LLM_STUB=1`. Confirms `ask` is unchanged
and the test-only `_retrieve` fork is gone (composition is the public `compose_answer`).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-ar.1 | ask unchanged | `COMPENDIUM_LLM_STUB=1 uv run python -m compendium ask "What is psychological safety?"` then an uncovered question | covered answers with citations + footer; uncovered refuses with gap + suggested action; both still write `query_traces` + `ask_traces` |
| arch-ar.2 | no test-only seam | `grep -rnE '_retrieve[ =:)]' compendium/ tests/` | no matches — composition is the public `compose_answer`, the same function `ask` composes through |

## Local profiler — stats / CPU / memory + stack verbs

Prerequisites: stores up; seeded corpus (at least one ingested source and a few
queries). All artifacts land in `~/.compendium/profiles` unless
`COMPENDIUM_PROFILE_DIR` overrides.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| prof.1 | Spans off by default | `uv run python -m compendium query "spaced repetition"` | no `profile` events on stderr; the query trace still records `latencies_ms` |
| prof.2 | Span switch (flag) | `uv run python -m compendium --timings query "spaced repetition"` | one JSON `profile` event per stage (`embed`, `pages_fanout`, …) on stderr |
| prof.3 | Span switch (.env) | add `COMPENDIUM_PROFILE=1` to `.env`, run prof.1's command, then remove it | same span events without any flag; removing restores silence |
| prof.4 | CPU profile | `uv run python -m compendium --profile index status` | command output unchanged; stderr shows `cpu profile written: …/index-<ts>.prof` plus a top-25 cumulative table; `python -m pstats <path>` loads it |
| prof.5 | Performance stats | `uv run python -m compendium profile stats --days 90` | retrieval per-stage avg/p95 + per-day counts, ask tokens/refusals/cost, curate runs, sync backlog, ingest outcomes; `--format json` emits one object |
| prof.6 | Ingest stage durations | ingest any fixture, then prof.5 again | the ingest table gains `ingest.parse` / `ingest.inspect` / `ingest.chunk` rows (from `sources.metadata["stage_ms"]`) |
| prof.7 | Memory arm/report | `uv run python -m compendium serve` in one shell; from another: `kill -USR1 <pid>`, run a few `/query` requests, `kill -USR2 <pid>` | daemon undisturbed; `mem-<ts>.txt` appears in the artifacts dir with traced size, RSS, and top growth sites |
| prof.8 | Stack verbs | `uv run python -m compendium stop` then `… start` then `… restart` | each delegates to `deploy/compendiumctl` (same output as calling it directly); exit codes propagate |

## Arch — chat envelope (behaviour-preserving)

Prerequisites: stores up; seeded corpus. Confirms the three real LLM clients
share one construction site + one call envelope, with output unchanged.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-ce.1 | Stub walk unchanged | `COMPENDIUM_LLM_STUB=1 uv run python -m compendium ask "What is psychological safety?"`, `… synth concept "<term>"`, `… curate run` | identical output to pre-fix: ask citations + footer, synth page written, curate report |
| arch-ce.2 | One construction site | `grep -rn "OpenAI(" compendium/` | exactly two matches: `model_clients.py` (the envelope) and `index/embedder.py` (embeddings, out of scope) |
| arch-ce.3 | Envelope speaks real OpenRouter | `uv run pytest -m live` (stubs unset, keys in `.env`) | 2 passed — the live tier exercises the real path through `chat()` |
| arch-ce.4 | Usage now logged for synth/extract | `COMPENDIUM_PROFILE=1` real `synth concept "<term>"` (or inspect stderr of a real `curate run`) | one `llm_usage` event with role/model/input_tokens/output_tokens |

## Arch — status probe routing (behaviour-preserving)

Prerequisites: none beyond the repo. Confirms the schedule + serve status
readers consume the service_unit probe seam with unchanged output.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-spr.1 | Schedule status unchanged | `compendium schedule install --every 30m` → `schedule status` → `uninstall` | field-for-field identical to v0.2-3.3: loaded/state/unit_path/interval 1800s/last_fired/next_fire |
| arch-spr.2 | Serve status unchanged | `compendium serve install` → `serve status` → `uninstall` | loaded/state/host/port/unit line as before |
| arch-spr.3 | Readers own no scheduler CLI | `grep -n "subprocess\|sys.platform" compendium/schedule/status.py compendium/api/service.py` | no matches — probing lives in `service_unit.probe_activity` |
| arch-spr.4 | Absent unit | `schedule status` with nothing installed | `state="absent"`, exit 1 |

## Arch — index-document shape (behaviour-preserving)

Prerequisites: stores up; seeded corpus. Confirms the one-declaration shape
changes no wire bytes and no rankings.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-ids.1 | Rankings unchanged | `reindex all`, then the standard covered query | identical coverage and top page to the pre-fix capture; golden tier identical |
| arch-ids.2 | Writer/mapping/reader pinned | `uv run pytest tests/test_indexes.py -q` | wire-freeze, constants-agreement, mapping-agreement, and preview-accessor tests all pass |
| arch-ids.3 | No raw field reads | `grep -n "f.get(" compendium/retrieve/pipeline.py` | no matches — retrieval reads hits through DisplayFields |

## Arch — facade coercion (behaviour-preserving)

Prerequisites: stores up; seeded corpus. Confirms ingest coercion + the
not-found convention live once in the facade, with the surface unchanged.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-fc.1 | Surface unchanged | run the v0.2-7 walk (or `deploy/ci-smoke.sh` layer 3) | byte-identical responses: b64 ingest auto-syncs, missing input → 400 with "ingest requires 'path' or 'content_base64'", unknown page → HTTP 404 / MCP null |
| arch-fc.2 | Transports coercion-free | `grep -n "b64decode\|import base64" compendium/api/http.py compendium/api/mcp.py` | no matches |

## v0.3 Phase 1 — Contradiction candidates (ADR-014)

Prerequisites: stores up; a corpus with at least one concept page and an
unlinked neighbour (the standard fixture corpus works). Stubs are fine
(`COMPENDIUM_LLM_STUB=1` proposes deterministically).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.3-1.1 | Propose, no edge | `compendium curate run`, then `curate list` and `graph status` | a `contradiction_candidate` signal (slugs + confidence + rationale in the payload); `CONTRADICTS: 0` |
| v0.3-1.2 | Approve writes the curator edge | `compendium curate resolve <id> --approve`, then `graph status` | `CONTRADICTS: 1`; the edge carries `extracted_by="curator"`; the signal is `addressed` |
| v0.3-1.3 | Never re-proposed | `compendium curate run` again | no new candidate for that pair (watermark + linked/proposed pre-filters) |
| v0.3-1.4 | Survives rebuild | `compendium graph rebuild`, then `graph status` | `CONTRADICTS: 1` (replayed from PostgreSQL, ADR-013) |
| v0.3-1.5 | Drop is recorded | propose another candidate (or seed one), `curate resolve <id> --drop`, re-run | signal `dropped`; the pair is never re-asked; no edge |

## v0.3 Phase 2 — Web UI (ADR-015)

Prerequisites: stores up; a seeded wiki; at least one open
`contradiction_candidate` (run the v0.3-1 walk first). Stubs are fine.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.3-2.1 | Launch, loopback only | `compendium web`; `lsof -nP -iTCP:8501 -sTCP:LISTEN` | the app serves on `http://127.0.0.1:8501`; the listener binds 127.0.0.1 only |
| v0.3-2.2 | Covered ask | Ask view: a corpus-covered question | the composed answer renders with `[n]` citations and the coverage footer |
| v0.3-2.3 | Refusal | Ask view: an off-corpus question (raise `ask.refuse_below_coverage` if the corpus is tiny) | the refusal renders with the gap and copy-paste suggested actions |
| v0.3-2.4 | Search + open a page | Search view: a covered query; Pages view: open the top result | ranked pages with coverage; the page renders frontmatter + Markdown body |
| v0.3-2.5 | Approve from the browser | Curation view: Approve on a `contradiction_candidate`; then `compendium graph status` | the `CONTRADICTS` count increments (curator provenance); the signal leaves the queue |

## v0.4 Phase 0 — Clear the deck

Prerequisites: none beyond a dev checkout (hermetic; no stores needed for
0.1; 0.2 wants the dev stack for a real `ask`, or runs as the unit tier).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.4-0.1 | Wire snapshots hold | `uv run pytest tests/test_wire_format.py -q` | 12 passed; any failure names the wire contract in its message |
| v0.4-0.2 | Unknown model is loud | `uv run pytest tests/test_ask.py -q` (unit), or set `SYNTHESIS_MODEL` to an unpriced name and run one `ask` against the dev stack | `unknown_model_rate` warning with the model name; `cost_estimate` records 0.0 |
| v0.4-0.3 | Mutants retired | `ls mutants`; `gh pr view 47 --json state -q .state` | `No such file or directory`; `CLOSED` |

## v0.4 Phase 1 — The single-point A/B (ADR-016)

Prerequisites: stores up; the fixture corpus seeded (the smoke walk's ingest +
reindex state). Stubs are fine. The chunk arm is validate-only.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.4-1.1 | Control arm fenced | `compendium query --help` | no `--arm` option on the supported surface |
| v0.4-1.2 | A/B over the fixtures | `compendium validate run --probes tests/fixtures/probes/probe-set.yaml` | per-query table (page vs chunk hit/recall/mrr), methodology header, aggregate row, exit 0 |
| v0.4-1.3 | Determinism | run v0.4-1.2 twice with `--format json`; diff the two | identical reports |
| v0.4-1.4 | Frozen guard | `compendium validate run --probes <an unfrozen yaml>` | refuses, names the freeze step, exit 1 |
| v0.4-1.5 | Harvest hygiene | `compendium validate harvest --out /tmp/probes` | `candidates.yaml` written under /tmp; `git status` clean |
| v0.4-1.6 | Real run (post-Track-A) | freeze a probe set; `compendium backup`; `validate run --probes ~/.compendium/probes/probe-set.yaml` | report readable against the pre-registered criteria |
