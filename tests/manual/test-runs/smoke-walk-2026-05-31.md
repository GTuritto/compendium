# Cumulative smoke walk — 2026-05-31

| Field | Value |
| --- | --- |
| Host | Mac mini Apple Silicon |
| OS | macOS 25.5.0 |
| Date | 2026-05-31 |
| Stack | live **populated dev** stack (not a fresh reset) — Postgres/OpenSearch/Qdrant/Memgraph via `docker compose` |
| Stubs (Phases 0–10, v0.2-3..7) | `COMPENDIUM_EMBED_STUB=1` / `COMPENDIUM_SYNTH_STUB=1` where noted; real embeddings for the access-surface live walk |
| Stubs (v0.2-1) | unset (real OpenRouter for both seams) |
| Smoke source | [`../smoke_test.md`](../smoke_test.md) |
| Merged through | v0.2 Phase 7 (PR #38) — access surface (MCP + HTTP) |

Bottom line: the full v0.1 (Phases 0–10) and v0.2 (Phases 1–7) smoke
surface passes on the merged stack. The one environment blocker found on
2026-05-30 (backup needs `pg_dump`) was **fixed this run** by
`brew link --force libpq`, and the v0.2 Phase 2 backup → drop-DB →
restore round-trip then passed end-to-end. Phase 8 (TUI) is a
full-screen interactive Textual app; it was verified via its headless
Pilot suite (`tests/test_tui.py`), which is the non-interactive
equivalent of scenarios 8.1–8.7.

## Method note

This walk ran against the **already-populated dev corpus**, not a fresh
reset, so absolute counts and coverage values differ from the
single-source numbers in `smoke_test.md` (coverage is the normalized
top-k mean and is corpus-dependent). Scenarios whose acceptance is a
behaviour or a top-page identity are reported PASS; scenarios whose
acceptance is an exact count against a clean corpus are reported
"PASS (behaviour); counts reflect the populated corpus".

## Automated umbrella suite

| Command | Result |
| --- | --- |
| `uv run pytest` (unit + integration + golden, live deselected) | **209 passed, 1 skipped, 2 deselected** |
| `uv run pytest -m live` (real OpenRouter) | **2 passed** (real embedder roundtrip + real synth prose) |
| `uv run pytest -m golden` | **3 passed** (baseline compare + per-query gate) |

The suite is the exact-assertion execution of every phase's behaviour on
isolated `compendium_test` / `compendium_golden` databases, and is itself
Phase 10 scenarios 10.1–10.4.

## v0.1 — Phases 0–10

| Phase | Result | Notes |
| --- | --- | --- |
| 0 — Skeleton | PASS | cold start + URLs (exit 0); missing-var → clean config error, no traceback; JSON logs, no secrets |
| 1 — Postgres | PASS (suite) | migration up/down + stub round-trip + views executed by `test_schema.py` on a throwaway DB (not re-run destructively on the dev DB) |
| 2 — Ingestion | PASS | idempotent re-ingest → `unchanged`; `--mine` provenance. 2.4 broken→`unchanged` here because the fixture was already ingested in a prior walk (failed-path covered by `test_ingestion.py`) |
| 3 — Wiki | PASS | `lint` 0 errors; stub `synth concept` wrote the page |
| 4 — Indexes | PASS | `reindex all` 42 indexed / 0 failed; `index status` drained; OpenSearch `body:psychological` hits |
| 5 — Retrieval | PASS | `query` ranked pages + coverage; `--format json` full shape; traces persisted |
| 6 — Memgraph | PASS | `graph rebuild` 32–33 nodes / 35 edges; `graph status` shows the four semantic edges at 0 (correct for v0.1) |
| 7 — Traces | PASS | trace list/show, read-only replay (ranking unchanged), promotions list |
| 8 — TUI | PASS (Pilot) | full-screen interactive app; verified via `tests/test_tui.py` Pilot (boots, all six screens reachable, help modal, keyboard ingest/synth/query/graph session). Raw launch also confirmed it renders the dashboard and runs its event loop. Not hand-walkable from a non-TTY agent shell |
| 9 — Curation | PASS | `curate run` writes a `graph_analysis_runs` row; open `low_coverage_query` signals listed by priority |
| 10 — Golden/CI | PASS | via the suite (10.1–10.4); `.github/workflows/ci.yml` present (10.5) |

## v0.2 — Phases 1–7

| Phase | Result | Notes |
| --- | --- | --- |
| 1 — Real models | PASS | `pytest -m live` 2 passed; real OpenRouter embeddings + synth confirmed (also exercised live via the ask + access-surface walks) |
| 2 — Backup / restore | PASS (after fix) | **Fix:** `pg_dump`/`pg_restore` were not on PATH; `brew link --force libpq` (libpq 18.4) put them on `/opt/homebrew/bin`. Then: backup writes a 165 KB `compendium.dump` + `vault.tar.gz` (2.1); rsync mirror to `/tmp/cdb-test` (2.2); rsync-failure isolation retains the local pair (2.3); **drop DB + wipe vault → `restore --force` fully recovered 6 pages in DB + vault** (2.4); `reindex all` + `graph rebuild` → query top-page identical (2.5); `backup install --at 03:15` plist `Hour=3/Minute=15`, idempotent uninstall (2.6) |
| 3 — Scheduled daemon | PASS | `schedule install` plist `StartInterval=3600`; reinstall `--every 30m` → `1800`; status; **launchd kick fired `curate run` → `graph_analysis_runs` +1**; idempotent uninstall (plist gone) |
| 4 — Inbox watcher | PASS | install → 7-dir layout + watcher; good PDF → `processed/<date>/`, corrupt → `failed/<date>/` + `.error`, `.crdownload` skipped, status counts, idempotent uninstall (inbox preserved) |
| 5 — Retrieval tuning | PASS | golden compare + per-query gate pass; normalization "The Psychological Safety concept" → `normalized_query` "psychological safety concept" |
| 6 — Composed answers (`ask`) | PASS | covered → answer + `[n]` citations + `ask_trace_id`; refusal path (threshold-demonstrated); chunked HTTP + buffered; real-model leg recorded model + token counts + a non-zero cost estimate, with the LLM-rewritten query visible in the trace |
| 7 — Access surface | PASS | `serve` (uvicorn, `127.0.0.1:8787`): `index_status`, `query`, bytes-`ingest` auto-sync (new source rank-1 immediately), `ask` buffered + `/ask/stream`, `page_list`/`page_get`/404; `mcp` over **real stdio**: `list_tools` (six verbs) + live `query`/`ask`; loopback-only confirmed (LAN-IP request refused) |

## Findings

1. **Backup prereq (fixed).** `compendium backup` requires `pg_dump`/`pg_restore`
   on PATH. On this host libpq 18.4 was installed but keg-only; `brew link
   --force libpq` made the binaries resolvable (persistently, via
   `/opt/homebrew/bin`). The smoke prereq note already documents this.
2. **Phase 8 is Pilot-verified, not hand-walked.** The TUI is a full-screen
   interactive app; the headless equivalent of 8.1–8.7 is
   `uv run pytest tests/test_tui.py` (Textual Pilot). Added a pointer to the
   Phase 8 section of `smoke_test.md`.
3. **Populated-corpus counts.** Running against the live dev corpus (not a
   fresh reset) means coverage/page-count values differ from the documented
   single-source numbers; top-page identities and behaviours match.
