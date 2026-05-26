# Tasks — phase-8-tui

Implements Phase 8 of `docs/COMPENDIUM_BUILD.md`. No schema migration: screens
read existing tables/views and call existing entry points. Task groups map to
the sub-phases (one commit per group, green at HEAD).

## 1. App shell, navigation, data layer, dashboard (8a)

- [ ] 1.1 Add `textual` to `pyproject.toml`; `uv lock`
- [ ] 1.2 `compendium/tui/data.py`: data-provider functions over the existing repository reads (counts, `v_sync_lag`, `v_recent_traces`, `v_failed_sources`, sources, pages, `v_open_curation_signals`) and the graph client
- [ ] 1.3 `compendium/tui/app.py`: the App with a screen registry, global bindings (per-screen nav + `?` help + `q` quit), and a footer; a `@work(thread=True)` helper for provider calls
- [ ] 1.4 `compendium/tui/screens/dashboard.py`: counts + sync lag + recent traces, with a refresh binding
- [ ] 1.5 `compendium tui` subcommand in `compendium/__main__.py`

## 2. Source list + ingest (8b)

- [ ] 2.1 `compendium/tui/screens/sources.py`: list sources with inspection status (failures distinguished)
- [ ] 2.2 Ingest action: a path input that runs `ingest(...)` in a worker and refreshes on completion; errors shown in-screen

## 3. Page list + synth (8c)

- [ ] 3.1 `compendium/tui/screens/pages.py`: list wiki pages, filterable by kind and status
- [ ] 3.2 Synth action: a kind+name input that runs `synthesize_concept`/`synthesize_topic` in a worker and refreshes; errors shown in-screen

## 4. Query workbench (8d)

- [ ] 4.1 `compendium/tui/screens/workbench.py`: a query input that runs `pipeline.query(text)` in a worker (persists a trace), renders the ranked pages, coverage, and fallback
- [ ] 4.2 Inspect the resulting trace (reuse the Phase 7 trace rendering): stages, fused ranking, gaps

## 5. Graph browser + curation queue (8e)

- [ ] 5.1 `compendium/tui/screens/graph.py`: search nodes by title/slug and walk typed edges N hops from a selection; report unreachable Memgraph gracefully
- [ ] 5.2 `compendium/tui/screens/curation.py`: read-only list over `v_open_curation_signals` (renders empty correctly); curator actions deferred to Phase 9

## 6. Tests and acceptance (8f)

- [ ] 6.1 Unit: data-provider functions (skip if Postgres unreachable) return the expected shapes for dashboard/sources/pages/curation
- [ ] 6.2 Pilot tests (`App.run_test()`): app boots; every screen is reachable via its binding; footer/help shows bindings; quit exits cleanly
- [ ] 6.3 Pilot session: open the ingest input, open the synth input, run a workbench query, open the graph browser — the scripted keyboard session drives without error (stub embedder; skip if stores unreachable)
- [ ] 6.4 Append the Phase 8 smoke section to `tests/manual/smoke_test.md`; run it (real-terminal launch + the keyboard-only daily-use session)
- [ ] 6.5 **Acceptance:** `compendium tui` starts, all six screens are reachable, key bindings work, and the keyboard-only session (ingest a source, inspect a trace, run a synth, browse the graph) completes. `uv run pytest` passes
