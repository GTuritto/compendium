## Why

Compendium has a full CLI surface (ingest, synth, query, graph, trace, page, promotions) but no persistent, navigable operational view. ADR-008 commits a keyboard-driven Textual TUI as the ops console: half the value of an ops surface is seeing several things at once — counts, sync lag, recent traces, a query workbench, the graph — which a single-shot CLI cannot give. Phase 8 builds that console over the data and operations Phases 0–7 already expose. It does not add new domain logic; it composes the existing repository reads, the Phase 5 pipeline, the Phase 6 graph, and the ingest/synth entry points into screens.

## What Changes

- **A Textual app launched by `compendium tui`** — keyboard-only (no mouse required), a global navigation bar to switch screens, and quit/help bindings. Blocking work (DB reads, graph queries, ingest, synth, retrieval) runs off the UI thread via Textual `@work(thread=True)`.
- **Six screens, one per operational concern** (per the build plan):
  - **Dashboard** — table counts, sync lag (`v_sync_lag`), recent traces (`v_recent_traces`).
  - **Source list** — sources with inspection status (failures from `v_failed_sources`); an **ingest** action (enter a path, run).
  - **Page list** — wiki pages filterable by kind, status, and lint state; a **synth** action (enter concept/topic name, run).
  - **Query workbench** — type a query, run the Phase 5 pipeline live (persisting a trace), and inspect the resulting trace (stages, fused ranking, coverage, fallback).
  - **Curation queue** — a read-only list over `v_open_curation_signals` (empty until Phase 9 feeds it); curator actions land in Phase 9.
  - **Graph browser** — search Memgraph nodes and walk typed edges N hops.
- **A data-provider layer** (`compendium/tui/data.py`) wrapping the existing repository reads and graph queries, so screens hold no SQL/Cypher.
- **No content editing in the TUI.** Wiki edits go through synth or a manual file edit + reindex, per the build plan.

## Capabilities

### New Capabilities

- `ops-console`: The keyboard-driven Textual ops console — app shell and navigation, the six screens, the data-provider layer, and the TUI-triggered ingest/synth actions, launched by `compendium tui`.

### Modified Capabilities

<!-- None. The TUI composes existing capabilities (ingestion, wiki, retrieval,
structural-graph, telemetry) and the operational views from Phase 1; no existing
capability's requirements change. -->

## Impact

- **New code:** `compendium/tui/` — `app.py` (App, navigation, bindings), `data.py` (data providers), `screens/` (dashboard, sources, pages, workbench, curation, graph); a `compendium tui` CLI subcommand in `compendium/__main__.py`.
- **New dependency:** `textual`. Tests use Textual's built-in async harness (`App.run_test()` + `Pilot`) — no additional test dependency.
- **No schema migration.** Screens read existing tables/views (`v_sync_lag`, `v_recent_traces`, `v_failed_sources`, `v_open_curation_signals`, `sources`, `wiki_pages`, `query_traces`) and call existing entry points (`ingest`, `synthesize_concept`/`synthesize_topic`, `pipeline.query`, the graph client).
- **Out of scope** (later phases): curator actions on signals — trigger-synth-from-signal, mark-addressed (Phase 9); semantic-edge annotation in the graph browser (Phase 9); any web UI (v0.2); editing wiki content in the TUI.
