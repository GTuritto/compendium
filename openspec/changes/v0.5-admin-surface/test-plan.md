# QA Test Plan — v0.5 Admin / Ops Surface in TUI + WebUI (ADR-020)

Generated with `/qa-test-planner`. Three tiers — **Unit** (hermetic + Pilot/
headless), **Smoke** (`tests/manual/smoke_test.md`), **Acceptance** (mapped to
the ADR-020 requirements). Every case names the sub-phase and the invariant.

## Scope

In: a WebUI dashboard (store/index counts + health) and safe ops (reindex,
graph rebuild, backup, inbox "process now"); TUI admin actions (the same safe
ops plus destructive source delete with confirmation and unit status); the
"process inbox now" recovery action on both UIs; the one-operations-seam rule
(TUI/WebUI call the CLI's operation functions, no copies). Out: tag controls
(deferred pending the tagging merge, PR #91); WebUI auth.

## Invariants under test

- **P1 (posture):** destructive ops (source delete, wipe, restore) and unit
  install/uninstall are NOT reachable from the WebUI / HTTP / MCP.
- **P2:** reindex / graph rebuild / backup are non-destructive (rebuild derived
  from canonical) and therefore allowed in the WebUI.
- **P3 (one seam):** CLI, TUI, and WebUI invoke the same operation entry points;
  no admin logic is duplicated in a UI.

## Unit tests

| ID | Sub-phase | Objective | Expected | Tier |
|----|-----------|-----------|----------|------|
| TC-ADM-U1 | seam / P1 | the WebUI module exposes no destructive verb | source-grep + import surface: no delete/wipe/restore/unit-install symbol called in `compendium/web/` | hermetic |
| TC-ADM-U2 | seam / P3 | the WebUI/TUI ops call the CLI seam | the dashboard/ops helpers resolve to `sync.reindex` / `graph.rebuild` / `backup` / `inbox.process` (same callables) | hermetic |
| TC-ADM-U3 | WebUI dashboard | dashboard data assembles counts/health | a headless render of the dashboard returns the `index_status` counts + store health without error | headless |
| TC-ADM-U4 | WebUI safe ops | a safe-op button calls its seam fn | clicking reindex/backup/process-inbox invokes the seam (mocked) and surfaces the result | headless |
| TC-ADM-U5 | TUI admin | the TUI admin actions fire the seam | Pilot: pressing the reindex / graph-rebuild / process-inbox / delete bindings invokes the seam (mocked) and reports | Pilot |
| TC-ADM-U6 | TUI delete | source delete is confirmed | Pilot: the delete action prompts and only deletes on confirm | Pilot |
| TC-ADM-U7 | inbox sweep | the sweep timer unit renders correctly | the inbox-sweep `.timer` descriptor renders `OnUnitActiveSec` + `Unit=compendium-inbox.service` (the Pi deploy) | hermetic |

## Smoke (append to `tests/manual/smoke_test.md` § v0.5 Admin)

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| v0.5-adm.1 | WebUI dashboard | open the WebUI; view the dashboard | store/index counts match `compendium index status` |
| v0.5-adm.2 | WebUI safe op | trigger reindex from the WebUI | reindex runs; counts refresh; no delete/wipe control present |
| v0.5-adm.3 | WebUI process-inbox | drop a file; click "process inbox now" | the file ingests and routes to processed/ |
| v0.5-adm.4 | WebUI has no destructive ops | inspect the WebUI surface | no delete / wipe / restore / unit-install control (P1) |
| v0.5-adm.5 | TUI full admin | in the TUI run reindex, graph rebuild, a confirmed source delete | each runs and reports; delete prompts first |
| v0.5-adm.6 | Inbox sweep backstop | drop a file the watcher misses; wait for the 10-min sweep | the sweep ingests it (no-op when empty) |

## Acceptance (ADR-020 requirements)

| ID | Requirement | Given / When / Then |
|----|-------------|---------------------|
| AC-ADM-1 | Destructive ops never on the no-auth surface | WHEN the WebUI/HTTP/MCP are inspected; THEN no delete/wipe/restore/unit-install (P1) |
| AC-ADM-2 | TUI exposes the full admin surface | WHEN the curator opens the TUI admin actions; THEN reindex, graph rebuild, backup, and a confirmed source delete are available and report results |
| AC-ADM-3 | WebUI dashboard + safe ops | WHEN a user opens the WebUI dashboard; THEN counts/health show and reindex/graph-rebuild/backup/process-inbox are offered |
| AC-ADM-4 | One operations seam | WHEN an op runs from CLI, TUI, WebUI; THEN all three call the same underlying function (P3) |
| AC-ADM-5 | Inbox recovery + self-healing | WHEN files sit unprocessed; THEN "process inbox now" (TUI/WebUI) drains them, and the periodic sweep drains missed files (no-op when empty) |

## Exit criteria

Unit cases green in the fast tier; the six smoke scenarios pass against the dev
stack; AC-ADM-1..5 demonstrated; P1–P3 hold; `ci-smoke.sh` green.
