# Phase 8 — TUI ops console: Implementation Plan

Date: 2026-05-26
Branch: `phase-8-tui` (off `main`)
OpenSpec change: `openspec/changes/phase-8-tui/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 8;
[docs/Compendium.md](../docs/Compendium.md) ADR-008.

## Goal

A keyboard-driven local console for the operations that matter day-to-day:
`compendium tui` launches a Textual app whose six screens are reachable by
keyboard, and the daily-use session (ingest a source, inspect a trace, run a
synth, browse the graph) is keyboard-only.

## Why this plan exists

Phases 0–7 expose every operation via the CLI, but an ops console's value is
seeing several things at once (ADR-008). This plan locks four decisions: (1) a
thin `compendium/tui/data.py` provider layer so screens hold no SQL/Cypher and
the providers are unit-testable without Textual; (2) all blocking work (DB,
graph, ingest, synth, retrieval) runs in `@work(thread=True)` workers so the UI
never freezes; (3) the workbench runs the real Phase 5 pipeline and persists a
trace (no parallel read-only path); (4) tests use Textual's `run_test()`/`Pilot`
harness (reachability + bindings + a scripted session) plus provider unit tests,
adding no test dependency. The curation-queue screen is a read-only shell now;
its curator actions are Phase 9.

## Branch + commit strategy

- Create `phase-8-tui` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 8a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 8 complete — TUI ops console`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### 8a — App shell, navigation, data layer, dashboard

**Purpose:** A launchable app with navigation and the first screen.

**Tasks:**

1. Add `textual` to `pyproject.toml`; `uv lock`.
2. `compendium/tui/data.py`: provider functions over the existing repository
   reads (counts, `v_sync_lag`, `v_recent_traces`, `v_failed_sources`, sources,
   pages, `v_open_curation_signals`) and the graph client.
3. `compendium/tui/app.py`: the App, screen registry, global bindings
   (`d/s/p/w/c/g` nav, `?` help, `q` quit), footer, and a `@work(thread=True)`
   helper.
4. `compendium/tui/screens/dashboard.py`: counts + sync lag + recent traces, with
   a refresh binding.
5. `compendium tui` subcommand in `compendium/__main__.py`.

**Files added:** `compendium/tui/{app,data}.py`, `compendium/tui/screens/dashboard.py`
**Files modified:** `compendium/__main__.py`, `pyproject.toml`, `uv.lock`
**Decision flagged:** mnemonic-letter nav with a visible footer; provider layer
holds all SQL.

### 8b — Source list + ingest

**Tasks:**

1. `screens/sources.py`: list sources with inspection status (failures shown).
2. Ingest action: a path input → `ingest(...)` in a worker → refresh; errors
   in-screen.

**Files added:** `compendium/tui/screens/sources.py`
**Decision flagged:** ingest reuses the existing `ingest` entry point verbatim.

### 8c — Page list + synth

**Tasks:**

1. `screens/pages.py`: list wiki pages, filterable by kind and status.
2. Synth action: kind+name input → `synthesize_concept`/`synthesize_topic` in a
   worker → refresh; errors in-screen.

**Files added:** `compendium/tui/screens/pages.py`
**Decision flagged:** no content editing in the TUI (synth/file+reindex only).

### 8d — Query workbench

**Tasks:**

1. `screens/workbench.py`: query input → `pipeline.query(text)` in a worker
   (persists a trace) → render ranked pages, coverage, fallback.
2. Inspect the resulting trace (reuse Phase 7 trace rendering): stages, fused
   ranking, gaps.

**Files added:** `compendium/tui/screens/workbench.py`
**Decision flagged:** the workbench persists a trace (every query is traced).

### 8e — Graph browser + curation queue

**Tasks:**

1. `screens/graph.py`: search nodes by title/slug, walk typed edges N hops;
   report unreachable Memgraph gracefully.
2. `screens/curation.py`: read-only list over `v_open_curation_signals` (renders
   empty correctly); curator actions deferred to Phase 9.

**Files added:** `compendium/tui/screens/{graph,curation}.py`
**Decision flagged:** curation queue is a read-only shell in Phase 8.

### 8f — Tests and acceptance

**Tasks:**

1. Unit: data-provider functions (skip if Postgres unreachable) return expected
   shapes.
2. Pilot tests: app boots; every screen reachable via its binding; help/footer
   shows bindings; quit exits cleanly.
3. Pilot session: open ingest input, open synth input, run a workbench query,
   open the graph browser — drives without error (stub embedder; skip if stores
   unreachable).
4. Append the Phase 8 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/test_tui.py`
**Files modified:** `tests/manual/smoke_test.md`

## Final file tree after Phase 8

```text
compendium/
  tui/
    __init__.py          (existing stub; gains exports)
    app.py               NEW — App, screen registry, global bindings, worker helper
    data.py              NEW — data-provider layer (DB + graph reads)
    screens/
      __init__.py        NEW
      dashboard.py       NEW — counts, sync lag, recent traces
      sources.py         NEW — source list + ingest action
      pages.py           NEW — page list (filters) + synth action
      workbench.py       NEW — query + live retrieval + trace inspect
      graph.py           NEW — node search + edge walk
      curation.py        NEW — read-only signal queue
  __main__.py            MOD — `compendium tui`
pyproject.toml           MOD — textual
uv.lock                  MOD
tests/
  test_tui.py            NEW
  manual/smoke_test.md   MOD — § Phase 8
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | data providers | dashboard/sources/pages/curation providers return expected shapes |
| 2 | pilot | boot + nav | app mounts; each screen reachable via its binding; footer shows bindings |
| 3 | pilot | quit | quit binding exits cleanly |
| 4 | pilot | ingest action | ingest input runs in a worker and the source list refreshes |
| 5 | pilot | synth action | synth input runs in a worker and the page appears |
| 6 | pilot | workbench | a query runs, renders ranked pages/coverage, and persists a trace |
| 7 | pilot | graph browser | node search + N-hop walk renders; unreachable handled |

## Per-phase smoke test

Appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 8.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 8.1 | Launch + navigate | `uv run python -m compendium tui`, press `d`/`s`/`p`/`w`/`c`/`g` | each screen renders; footer shows bindings; no mouse used |
| 8.2 | Dashboard | open dashboard, press refresh | counts, sync lag, and recent traces render |
| 8.3 | Ingest a source | source list → ingest action → enter `tests/fixtures/sample.md` | the source appears with inspection status after the worker completes |
| 8.4 | Run a synth | page list → synth action → `concept` `psychological safety` (`COMPENDIUM_SYNTH_STUB=1`) | the concept page appears in the list |
| 8.5 | Workbench query | workbench → type `psychological safety` → run | ranked pages + coverage render; a new trace shows on the dashboard |
| 8.6 | Browse the graph | graph browser → search a source → walk 2 hops | reachable nodes and typed edges render |
| 8.7 | Quit | press `q` | the app exits cleanly to the shell |

## Out of scope for Phase 8 (do NOT build)

- Curator actions on signals (trigger synth from a signal, mark addressed) — Phase 9.
- Semantic-edge annotation in the graph browser — Phase 9.
- Editing wiki content in the TUI (ADR-008) — edits go through synth or file + reindex.
- A web UI — v0.2.
- Promotion/reindex actions in the TUI — remain CLI in v0.1 (results visible via dashboard/page list).

## Open questions — resolved at the review gate (2026-05-26)

1. **Navigation bindings.** RESOLVED: mnemonic letters (`d/s/p/w/c/g`) with a
   visible footer.
2. **Workbench persistence.** RESOLVED: the workbench persists each run as a
   trace (every query is traced).
3. **Write actions in v0.1.** RESOLVED: ingest and synth only; promotion and
   reindex stay CLI.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 8 met.
- [ ] PR marked ready for review.
