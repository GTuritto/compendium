# Cumulative smoke walk — 2026-06-01 (v0.1 Phase 0 → v0.2 Phase 8)

| Field | Value |
| --- | --- |
| Host | Mac mini Apple Silicon |
| OS | macOS 25.5.0 |
| Date | 2026-06-01 |
| Branch | `v0.2-phase-8-extract` (PR #40; all Phase 8 code present) |
| Stack | live **populated dev** stack via `docker compose` (not a fresh reset) |
| Stubs | `COMPENDIUM_EMBED_STUB=1` / `COMPENDIUM_SYNTH_STUB=1` where noted; real OpenRouter for the v0.2-1 live tier |
| Smoke source | [`../smoke_test.md`](../smoke_test.md) |

Bottom line: the full v0.1 (Phases 0–10) and v0.2 (Phases 1–8) smoke surface
passes on the Phase 8 branch, including the new autonomous edge extraction.

## Automated umbrella suite

| Command | Result |
| --- | --- |
| `uv run pytest` (unit + integration + golden) | **222 passed, 2 deselected (live)** |
| `uv run pytest -m live` | **2 passed** (real embedder + synth) |
| `uv run pytest -m golden` | passed |

Exact-assertion coverage of every phase's behaviour on isolated
`compendium_test` / `compendium_golden` databases (includes Phase 8:
`tests/test_extract.py`, 12 tests).

## v0.1 — Phases 0–10 (live CLI)

| Phase | Result |
| --- | --- |
| 0 Skeleton | PASS (cold start + URLs) |
| 1 Postgres | PASS (migration up/down + round-trip via `test_schema` in the suite) |
| 2 Ingestion | PASS (idempotent re-ingest) |
| 3 Wiki | PASS (lint 0 errors) |
| 4 Indexes | PASS (`reindex all` 42 indexed; OpenSearch body query hits) |
| 5 Retrieval | PASS (`query` + `--format json` full shape) |
| 6 Memgraph | PASS (`graph rebuild` + `graph status`) |
| 7 Traces | PASS (`trace list`) |
| 8 TUI | PASS (Pilot: `pytest tests/test_tui.py`, 3 passed — headless equivalent of 8.1–8.7) |
| 9 Curation | PASS (`curate run`) |
| 10 Golden/CI | PASS (via the suite) |

## v0.2 — Phases 1–8

| Phase | Result |
| --- | --- |
| 1 Real models | PASS (`pytest -m live` 2 passed) |
| 2 Backup / restore | PASS — backup (195 KB dump) → drop DB + wipe vault → `restore --force` (6 pages recovered) → `reindex all` + `graph rebuild` → **identical top page + score** (`0.03279`); `backup install`/`uninstall` clean |
| 3 Scheduled daemon | PASS — install (`StartInterval=1800`), status, **launchd kick wrote a `graph_analysis_runs` row** (25→26), idempotent uninstall |
| 4 Inbox watcher | PASS — install + 7-dir layout, good PDF → `processed/`, corrupt → `failed/` + `.error`, idempotent uninstall |
| 5 Retrieval tuning | PASS (`pytest -m golden`; normalization verified earlier) |
| 6 Composed answers (`ask`) | PASS (covered → answer + citations + `ask_trace_id`) |
| 7 Access surface | PASS — `serve` `/index_status` + `/query` + `/ask`; `mcp` `list_tools` returns six verbs (full 8-scenario walk done in the access-surface session) |
| 8 Autonomous edge extraction | PASS — cold-start `curate run` wrote 5 `RELATED_TO` with provenance; curator edge protected; structural pre-filter (0 overlap); expansion traverses an extracted edge; incremental run quiet; reversible by predicate (delete `llm conf<0.95` → curator survives) |

## Findings

1. **Test suite shares the dev derived stores.** `pytest` (golden / live /
   integration tiers) recreates the shared OpenSearch / Qdrant / Memgraph
   collections with test corpora, so after a test run the dev corpus's derived
   indexes are clobbered (e.g. Qdrant `pages` left with the 2-page golden
   corpus). The dev **PostgreSQL** is unaffected (tests use `compendium_test` /
   `compendium_golden`). Remedy: run `compendium reindex all` (+ `graph rebuild`)
   before dev CLI work that follows a test run. This (not the backup/restore)
   was the cause of the earlier "kNN found 0 neighbours" during Phase 8 — the
   code keys Qdrant page points by `wiki_pages.id`, verified `point ids == page
   ids` after a clean reindex.
2. **Bug found + fixed during the Phase 8 walk (commit 295dd05):** `graph link`
   wrote curator edges without an `extracted_by` property, so the extractor's
   protection (keyed on `extracted_by=="curator"`) did not fire and overwrote a
   curator edge. Fix: the extractor now protects **any non-`llm` edge**, and
   `graph link` stamps `extracted_by="curator"`. Regression tests added.
3. **Phase 8 launchd kick timing.** The scheduled `curate run` now also runs the
   real-LLM extractor over the dev corpus, so a kicked fire can take >8 s; poll
   ~30 s when verifying the `graph_analysis_runs` increment.

Environment left clean: dev DB 6 pages, Qdrant 6 page points (consistent), no
LaunchAgents, no `serve` process, git tree clean.
