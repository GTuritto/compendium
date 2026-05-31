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
