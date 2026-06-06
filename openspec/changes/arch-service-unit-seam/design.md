## Context

This is the first of the post-v0.2 architecture-deepening changes (architecture review 2026-06-06, candidate 1). It consolidates the four OS-service lifecycle implementations introduced across v0.2 Phase 2 (backup), Phase 3 (curate, ADR-012), Phase 4 (inbox), and the post-v0.2 deployment tooling (serve). It depends on nothing those phases did not already ship; it adds no behaviour.

The two prior architecture reviews (`docs/architecture/review-2026-05-26{,-2}.md`) did not cover this code — three of the four services (serve, and the always-on framing) postdate them. This change does not touch any of their settled verdicts (repository.py stays shallow; the sync/async client split stays).

The deepening target, in the review's vocabulary: four **shallow** families whose install/uninstall/status interface is nearly as complex as the implementation, with the one genuinely-varying axis (the **trigger**) scattered as per-OS branches instead of sitting behind a single **seam**. Two **adapters** (launchd, systemd) already exist; this change gives them one **interface** so a change to the lifecycle has **locality** (fixed once) and a new service has **leverage** (a descriptor, not a copy-paste).

## Goals / Non-Goals

**Goals:**

- One `compendium/service_unit/` module exposing `install(descriptor)` / `uninstall(descriptor)` / `status(descriptor)` over a `UnitDescriptor` + closed `Trigger` taxonomy, with launchd and systemd adapters behind it.
- Behaviour preservation: identical labels, file paths, unit content, idempotency, CLI verbs, and rendered output for all four services on both platforms.
- One `ServiceUnitError(step, detail)` and one `UnitStatus` replacing four and three respectively.
- The lifecycle testable without a real scheduler (adapters render to strings; subprocess behind an injectable `Runner`).
- Net deletion: the four `_platform`/`_repo_root` copies, four macOS dances, four Linux generators, and duplicate status parsers removed.

**Non-Goals:**

- Any change to ADR-012's posture, the CLI surface, or the render seam (PR #22).
- In-process scheduling / the Phase-7 access-surface absorption (separate future change).
- A Windows adapter (the current darwin/linux-only rejection is preserved).
- Touching backup's rsync, inbox's routing, serve's app, or the cadence/`parse_time` parsers beyond moving where they are called.

## Decisions

### Decision: a `compendium/service_unit/` package, mirroring `compendium/db/`

The seam lives in its own package, the operational analog of `db/` (one place that owns a cross-cutting concern with raw access underneath). Public surface in `__init__.py`: `install`, `uninstall`, `status`, `ServiceUnitError`, `UnitStatus`, `UnitDescriptor`, and the `Trigger` types. Each public function dispatches on platform exactly once (the only surviving `_platform()` call) and delegates to the launchd or systemd adapter.

**Alternative considered:** a `compendium/util/` grab-bag of shared helpers (`osdetect.py`, `osstatus.py`) that the four modules import piecemeal. Rejected — that leaves four lifecycle ladders that merely share leaf helpers; the duplication of the *lifecycle* (the install/uninstall/status dance) survives. The win is a deep module that owns the whole lifecycle, not shared leaves under four shallow ones.

### Decision: the `Trigger` is a closed taxonomy of four cases

The only axis that varies across the services becomes an explicit, closed set of dataclasses:

- `Interval(seconds: int)` — macOS `StartInterval`; Linux `.timer` with `OnUnitActiveSec` + `OnBootSec` + `Persistent=true`.
- `Calendar(hour: int, minute: int)` — macOS `StartCalendarInterval`; Linux `.timer` with `OnCalendar=*-*-* HH:MM:00`.
- `WatchPaths(paths: list[Path])` — macOS `WatchPaths`; Linux `.path` with one `PathChanged=` per path + a paired `.service`.
- `AlwaysOn()` — macOS `RunAtLoad=true` + `KeepAlive=true`; Linux `.service` with `Restart=always` + `RestartSec` into `default.target`.

The adapter derives the **unit type** from the trigger: `Interval`/`Calendar` → timer+service; `WatchPaths` → path+service; `AlwaysOn` → service-only. This is the single source of the timer-vs-path-vs-service decision that is currently implicit across four modules.

**Alternative considered:** a free-form `dict` of plist/unit keys per service. Rejected — it reintroduces per-service knowledge of plist internals and defeats the type-checked, golden-testable rendering. A closed taxonomy is exhaustively testable (four cases × two adapters = eight golden renders).

### Decision: `UnitDescriptor` is the whole interface a service must know

```text
UnitDescriptor(
    label: str,              # com.compendium.<svc>  (macOS label + identity)
    linux_basename: str,     # compendium-<svc>      (systemd unit file stem)
    description: str,        # human/[Unit] Description
    program_args: list[str], # the command the unit runs
    working_dir: Path,
    trigger: Trigger,
    log_basename: str | None = None,  # macOS StandardOut/ErrPath stem; None = no redirect
)
```

A service builds this and calls the seam. Everything the four modules currently hand-render (plist XML, systemd sections, file paths under `~/Library/LaunchAgents` or `~/.config/systemd/user`) is derived by the adapters from the descriptor. `program_args` keeps the existing `uv run --project <repo> python -m compendium <verb> …` shape; `_repo_root()` survives once, as a helper the descriptor builders call to fill `working_dir`/`program_args`.

### Decision: an injectable `Runner` makes the lifecycle testable

The adapters do not call `subprocess.run` directly; they call through a `Runner` protocol (`run(args) -> CompletedProcess`-like). The default runner shells out exactly as today (`capture_output=True, text=True, check=False`); tests inject a fake that records invocations and returns canned output. This is the internal seam that lets the install/uninstall/status dances be unit-tested (assert the right `launchctl`/`systemctl` argv, simulate non-zero exit → `ServiceUnitError`) without a scheduler present. Rendering is separated from running so unit content is golden-testable independently.

**Alternative considered:** monkeypatching `subprocess.run` in tests (the current approach in `test_schedule.py`). Acceptable but leaves the seam implicit; an explicit `Runner` documents the boundary and is reused by all four services' tests.

### Decision: one `ServiceUnitError` and one `UnitStatus`

`ServiceUnitError(step, detail)` replaces `ScheduleError` (×2), `InboxError`, `ServiceError`. The four step vocabularies (`platform`, `launchctl_bootstrap`, `systemctl_enable`, …) are preserved as `step` values, so log shape and error detail are unchanged. `UnitStatus` carries the union of the three current shapes as optional fields (`loaded: bool`, `state: str | None`, `last_exit: int | None`, plus trigger-specific extras like `interval_seconds`, `next_fire`, `last_fire`, and a `raw` blob), with a `to_dict()` that the render layer consumes. Each service's status verb maps the shared status into the JSON the CLI already prints.

**Migration note on names:** to keep blast radius small and the CLI output byte-identical, the per-service public names that the CLI imports (`ScheduleResult`, `install_schedule`, `install_watcher`, `install_service`, `ScheduleStatus`, `InboxStatus`, `ServiceStatus`) are preserved as thin shims/aliases over the shared types during migration. A later cleanup may drop the aliases; this change does not, to keep it behaviour-preserving and reviewable.

### Decision: migrate one service per sub-phase, green at each step

The seam lands first with full tests and zero callers changed (sub-phase a). Then each service migrates in its own commit (b–e), with that service's existing test module (`test_schedule.py`, `test_backup.py`, `test_inbox.py`, `test_serve_service.py`) staying green and its rendered output unchanged. Dead code is deleted only after its caller delegates (sub-phase f). This keeps every commit green and each diff small enough to verify that behaviour is preserved.

## Risks / Trade-offs

- **Behaviour drift during migration.** Mitigation: golden tests assert the adapter renders byte-identical plist/unit content to what each module produces today (captured as fixtures before the migration), so a render regression fails loudly. Labels and file paths are asserted equal to the current constants.
- **Hermetic testing of subprocess.** Mitigation: the `Runner` seam; CI never invokes a real `launchctl`/`systemctl`. A manual smoke on macOS (primary host) confirms real install/uninstall/status for all four.
- **Cross-platform coverage in CI.** CI runs on Linux; macOS rendering is covered by golden string tests (platform-independent) and exercised manually on the primary host, as the existing modules already are.
- **Name-alias debt.** Keeping the old public names as shims is deliberate scope control; flagged as a follow-up, not left silent.

## Migration Plan

Behaviour-preserving, no data or schema involved. Land the seam (a), migrate curate → backup → inbox → serve (b–e) one commit each with that service's tests green, then delete dead helpers and refresh docs (f). No deploy step; the generated units are identical, so an already-installed service keeps working and a reinstall produces the same files. Rollback is reverting the branch — no migration to undo.

## Open Questions

- Should the old per-service type names (`ScheduleResult`, `InboxStatus`, …) be dropped in this change or left as aliases for a later cleanup? (Plan: keep as aliases here; flag the cleanup.)
- Should a short ADR record the seam (it implements ADR-012 rather than deciding anything new)? (Plan: no new ADR; note the consolidation in ADR-012's text and the operational docs. Revisit if the Phase-7 absorption wants a decision record.)
