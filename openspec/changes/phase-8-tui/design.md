## Context

This change implements Phase 8 (TUI ops console, workstream H) of `docs/COMPENDIUM_BUILD.md`. It depends on Phases 0, 2, 3, 5, 6, and 7 — it composes their entry points and reads into a single console. The screen list and constraints are specified in `docs/Compendium.md` ADR-008 and Part IV Phase 8 and are implemented faithfully.

ADR-008 is the governing decision: the ops console is a keyboard-driven Textual TUI launched by `compendium tui`, no mouse required, no web UI in v0.1. Postgres is where operational truth lives, so the TUI reads almost everything from Postgres (plus Memgraph for the graph browser). Obsidian remains the read view for wiki content; the TUI does not edit content.

## Goals / Non-Goals

**Goals:**

- `compendium tui` launches a Textual app; all six screens are reachable by keyboard; quit/help bindings work.
- The acceptance keyboard-only session works: ingest a source, inspect a trace, run a synth, browse the graph — no mouse.
- Blocking work never freezes the UI (runs via `@work(thread=True)`).

**Non-Goals:**

- Curator actions on signals (trigger synth from a signal, mark addressed) — Phase 9; Phase 8 ships the read-only queue screen.
- Semantic-edge annotation in the graph browser — Phase 9.
- Editing wiki content in the TUI — out by ADR-008 (edits via synth or file + reindex).
- A web UI — v0.2.
- New domain logic — the TUI only composes existing capabilities.

## Decisions

### Decision: a thin data-provider layer; screens hold no SQL or Cypher

`compendium/tui/data.py` exposes plain functions returning plain data (dicts/lists/dataclasses) for every screen: dashboard counts + sync lag + recent traces, source rows + failures, page rows with filters, the query-workbench result, curation signals, and graph node/edge reads. Each wraps the existing `compendium/db/repository.py` reads, the Phase 6 graph client, and the Phase 5/7 entry points. Screens call these providers (never the DB directly), so the UI layer stays declarative and the providers are unit-testable without Textual. This mirrors how `compendium/retrieve/` and `compendium/trace/` sit over `compendium/db/`.

### Decision: blocking work runs in worker threads, results marshalled to the UI

Every provider call, ingest, synth, and retrieval run inside a Textual `@work(thread=True)` worker; the worker computes off the UI thread and posts the result back (via `call_from_thread` / message) so the event loop never blocks (CLAUDE.md: "Textual offloads blocking DB work with `@work(thread=True)`"). The synchronous `psycopg`/graph/pipeline code is reused unchanged — the TUI is the only place that needs the threading wrapper, and it stays in the worker boundary.

### Decision: an App with a screen registry and global navigation bindings

`compendium/tui/app.py` defines the App with a `SCREENS` registry and global key bindings: a digit or letter per screen (e.g. `d` dashboard, `s` sources, `p` pages, `w` workbench, `c` curation, `g` graph), `?` for help, `q` to quit. A persistent footer shows the active bindings. Each screen is a `Screen` subclass in `compendium/tui/screens/` owning its layout, its screen-local bindings (e.g. ingest/synth actions, filters), and its data-provider calls. New screens register in one place, keeping navigation uniform.

### Decision: the workbench runs the real pipeline and persists a trace

The query workbench types a query and runs `pipeline.query(text)` (persist=True, the default) so the run is a real, traced query — then renders the fused ranking, coverage, fallback, and a link into the trace (the Phase 7 `trace show` rendering). It does not re-implement retrieval or invent a read-only mode; "inspect the trace" reuses the persisted trace. This keeps the "every query is traced" invariant and gives the workbench and the dashboard's recent-traces list a shared source.

### Decision: ingest and synth are the TUI's only write actions in v0.1

The acceptance names ingest and synth as keyboard-only tasks, so the source-list screen has an **ingest** action (path input → `ingest(...)` in a worker → refresh) and the page-list screen has a **synth** action (kind + name input → `synthesize_concept`/`synthesize_topic` in a worker → refresh). These reuse the existing functions verbatim. Promotion and reindex remain CLI operations in v0.1 (the TUI can surface their results via the dashboard/page list); wiring promotion into the page list is a small Phase 9/later addition, not required by the Phase 8 acceptance.

### Decision: the curation queue is a read-only shell

The curation-queue screen renders `v_open_curation_signals` (kind, priority, payload summary, created_at). Until Phase 9's slow loop writes signals the list is empty, which is correct and reachable. The curator actions (select a signal, trigger synth pre-populated from its payload, mark addressed) are Phase 9; building the read-only shell now satisfies "all listed screens reachable" without pulling Phase 9 logic forward.

### Decision: tests use Textual's Pilot harness plus provider unit tests

The data providers are unit-tested directly (plain functions over the DB, skip if Postgres is unreachable). The app and screens are tested with Textual's async `App.run_test()` + `Pilot`: assert the app boots, each screen is reachable via its binding, the footer/help shows bindings, and a scripted keyboard session (open ingest, open synth, run a workbench query, open the graph browser) drives without error. No snapshot dependency — the assertions target reachability and state, not pixel layout, matching the acceptance.

## Risks / Trade-offs

- **TUI tests can be flaky/timing-sensitive** → `run_test()` is deterministic (it pumps the event loop under test control); provider calls are awaited via the worker completion, and tests assert observable widget state, not timing.
- **A screen's provider raising would crash the app** → providers run in workers; a worker failure is caught and shown as an error notification/state in the screen, never an unhandled crash of the app.
- **Textual is a sizeable new dependency** → justified by ADR-008 (Textual is the committed TUI framework, already in the Part IV stack table); it is a single well-maintained package.
- **Eventual consistency: the dashboard can show stale sync/index counts** → Accepted (ADR-005); the dashboard has a manual refresh binding, and counts are labelled as point-in-time.
- **Headless/CI environments** → `run_test()` runs without a real terminal; the manual smoke test covers a real terminal launch.

## Migration Plan

No schema migration. Add `textual` to `pyproject.toml` and `uv lock`. Add a `compendium tui` subcommand. Rollback is removing `compendium/tui/` (beyond the stub), the `tui` subcommand, and the dependency; nothing else is touched.

## Open Questions

- **Navigation binding scheme.** Letters mnemonic to each screen (`d/s/p/w/c/g`) versus number keys (`1`–`6`). The plan uses mnemonic letters with a visible footer; confirm at the review gate.
- **Workbench trace persistence.** The workbench persists each run as a trace (consistent with "every query is traced"). Confirm that is wanted versus a read-only workbench mode (the plan persists).
