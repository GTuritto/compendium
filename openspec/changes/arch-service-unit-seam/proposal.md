## Why

ADR-012 ships Compendium as four always-on personal-LAN services managed by launchd (macOS) or systemd (Linux): `backup` (`com.compendium.backup`), `curate` (`com.compendium.curate`), `inbox` (`com.compendium.inbox`), and `serve` (`com.compendium.serve`). Each was built in its own phase, and each independently reimplements the same OS-service lifecycle: detect the platform, render a plist or systemd unit, `launchctl bootstrap` / `systemctl --user enable --now`, parse the scheduler CLI for status, and tear down idempotently.

The duplication is verified, not inferred:

- `_platform()` and `_repo_root()` are byte-for-byte copies in all four modules (`backup/schedule.py:55,66` · `schedule/install.py:39,50` · `inbox/install.py:51,62` · `api/service.py:63,71`).
- The same structured `(step, detail)` exception is declared four times under four names: `ScheduleError` (twice — `backup/schedule.py:26` and `schedule/cadence.py:19`), `InboxError` (`inbox/install.py:33`), `ServiceError` (`api/service.py:33`).
- `launchctl` is driven from five files; the macOS `bootout`-then-`bootstrap` install dance and the `bootout`-then-`unlink` uninstall dance are near-identical across all four.
- Each family ships its own status dataclass (`ScheduleStatus`, `InboxStatus`, `ServiceStatus`) and its own launchctl/systemctl output parsing.

The four services differ in exactly one place — how the unit is **triggered** — and nowhere else:

| Service | Label | macOS trigger | Linux unit | Linux trigger |
| --- | --- | --- | --- | --- |
| curate | `com.compendium.curate` | `StartInterval=N` | `.timer`+`.service` | `OnUnitActiveSec=N`, `Persistent` |
| backup | `com.compendium.backup` | `StartCalendarInterval` (HH:MM) | `.timer`+`.service` | `OnCalendar=*-*-* HH:MM:00` |
| inbox | `com.compendium.inbox` | `WatchPaths[]` | `.path`+`.service` | `PathChanged=[]` |
| serve | `com.compendium.serve` | `RunAtLoad`+`KeepAlive` | `.service` | `Restart=always`, `default.target` |

This is the shape of a **missing seam**: behaviour that genuinely varies (the trigger) expressed four times as scattered per-OS branches, wrapped in four copies of identical lifecycle code. Two real adapters already exist in the wild (launchd, systemd) — the seam is real, not hypothetical. Adding a fifth service (a periodic export daemon, say) today means copy-pasting the whole skeleton again.

This change is behaviour-preserving. The labels, file paths, unit content, idempotency, and CLI output stay exactly as they are; only the implementation collapses from four ladders into one seam with two adapters.

## What Changes

- **A new deep module** `compendium/service_unit/` — the analog of `compendium/db/` for OS-managed units. It exposes one interface, `install` / `uninstall` / `status`, over a small `UnitDescriptor` value object and a closed `Trigger` taxonomy, with exactly two adapters (launchd, systemd) behind it. One structured `ServiceUnitError(step, detail)` replaces the four error classes. One `UnitStatus` dataclass (optional fields per trigger) replaces the three status dataclasses.
- **The `Trigger` taxonomy** captures the only thing that varies: `Interval(seconds)`, `Calendar(hour, minute)`, `WatchPaths(paths)`, `AlwaysOn()`. The adapter chooses the unit type from the trigger (timer+service / path+service / service-only) and renders the platform-specific keys.
- **A `Runner` seam inside the adapters** so the `launchctl` / `systemctl` calls are injectable. Adapters render units to strings (golden-testable) and shell out via the runner, so the lifecycle is testable without a real scheduler.
- **The four services shrink to descriptor builders.** `schedule/install.py`, `backup/schedule.py`, `inbox/install.py`, and `api/service.py` each build a `UnitDescriptor` (their label, basename, program args, working dir, and trigger) and delegate to `service_unit`. Their genuinely-unique logic stays put: backup's `parse_time` / rsync, inbox's `INBOX_KINDS` routing, serve's host/port, the cadence parser. Public function names the CLI calls (`install_schedule`, `install_watcher`, `install_service`, …) are preserved.
- **Status parsing is unified.** The launchctl/systemctl output parsing (currently in `schedule/status.py` plus ad-hoc copies in `inbox/install.py` and `api/service.py`) moves into one place behind the seam; the per-service status verbs delegate.
- **Dead code is deleted.** The four `_platform()` / `_repo_root()` copies, the four macOS install/uninstall dances, the four Linux unit generators, and the duplicate status parsers are removed once their callers delegate.
- **Operational docs are refreshed** (`docs/operations/{backup-restore,scheduled-curation,inbox,access-surface}.md` or their equivalents) to describe the one shared mechanism, and the smoke test gains a "four services still install/uninstall/status identically" check.

## Capabilities

### New Capabilities

- `os-service-unit`: the `compendium/service_unit/` seam — the `UnitDescriptor` + `Trigger` taxonomy, the `install` / `uninstall` / `status` interface, the launchd and systemd adapters with an injectable `Runner`, the single `ServiceUnitError` and `UnitStatus`. Behaviour-preserving across all four services on both platforms.

### Modified Capabilities

<!-- No behaviour change. The four services (backup, curate, inbox, serve)
keep their labels, file paths, unit content, CLI verbs, idempotency, and
output. They are re-expressed as descriptor builders over the new seam.
ADR-012's posture (always-on personal-LAN services under launchd/systemd)
is unchanged; this consolidates its implementation. -->

## Impact

- **New code/files:** `compendium/service_unit/__init__.py` (public surface + `ServiceUnitError` + `UnitStatus`), `descriptor.py` (`UnitDescriptor` + `Trigger`), `launchd.py` (macOS adapter), `systemd.py` (Linux adapter), `runner.py` (the injectable subprocess seam); `tests/test_service_unit.py`.
- **Modified files:** `compendium/schedule/install.py` + `status.py`, `compendium/backup/schedule.py`, `compendium/inbox/install.py` + `status.py`, `compendium/api/service.py` (all become descriptor builders over the seam); `compendium/schedule/cadence.py` (keep the parser; drop its duplicate `ScheduleError` in favour of the shared one, or alias it); `docs/operations/*` for the four services; `tests/manual/smoke_test.md`; `CLAUDE.md` (deployment-tooling sentence notes the shared seam).
- **No schema migration. No new runtime dependency.** Pure stdlib (`subprocess`, `pathlib`, `sys`).
- **No CLI change.** `compendium {backup,schedule,inbox,serve} install/uninstall/status` keep their flags, exit codes, and rendered output. The render layer (PR #22 seam) is untouched.
- **Out of scope:**
  - **Changing the deployment posture** — still launchd/systemd, still loopback/stdio, still single-user (ADR-012, ADR-011). No new transport, no LAN exposure.
  - **In-process scheduling** — the Phase-7 "absorb the schedule into the access surface" refactor is a *separate* future change; this seam makes that absorption tractable but does not perform it.
  - **A `compendium serve` behaviour change** — serve keeps `RunAtLoad`+`KeepAlive` / `Restart=always`; only its install/uninstall/status wiring moves.
  - **Windows support** — `_platform()` rejects non-darwin/linux today; the seam preserves that rejection, it does not add a third adapter.
