## Why

v0.1's curation slow loop is on-demand: the curator runs `compendium curate run` whenever they remember. In practice that means the corpus's "thin grounding" and "low coverage" signals only surface when the curator is already at the keyboard — exactly when there is least time to react. v0.2's posture (ADR-012, always-on personal service) wants the slow loop firing on a schedule, without manual invocation, so curation signals accumulate even while the curator is doing something else and are ready to drain when they sit down.

Phase 3 ships the smallest mechanism that satisfies "scheduled by default": a `compendium schedule install [--every 1h]` verb that writes an OS-native user-level scheduler unit (launchd LaunchAgent on macOS, systemd user timer + service on Linux). The unit fires `compendium curate run` on the configured cadence. A symmetric `compendium schedule uninstall` removes the unit; `compendium schedule status` reports whether the unit is loaded and when it last and next fires. The unit survives a host reboot. The CLAUDE.md and ADR-012 documentation updates land the "no daemon" rule's posture-specific exception that makes this phase legitimate.

## What Changes

- **A `compendium schedule install [--every <interval>]` CLI verb.** Writes a per-OS scheduled unit that fires `compendium curate run` on the configured cadence.
  - macOS: `~/Library/LaunchAgents/com.compendium.curate.plist`, loaded via `launchctl bootstrap gui/<uid>`. Cadence expressed as `StartInterval` (seconds), matching the parsed interval.
  - Linux: `~/.config/systemd/user/compendium-curate.{service,timer}`, enabled via `systemctl --user enable --now`. Cadence expressed as `OnUnitActiveSec`, matching the parsed interval; `Persistent=true` so a missed fire catches up after a host wake.
  - Cadence parsing accepts `Nh`, `Nm`, `NhMm` (for example `1h`, `30m`, `2h30m`); minimum granularity is one minute; default is `1h` when `--every` is omitted.
- **A `compendium schedule uninstall` CLI verb.** Removes the unit. Idempotent — re-running after the unit is gone reports "not installed" and exits 0.
- **A `compendium schedule status` CLI verb.** Reports the unit's state (loaded / not installed) and last/next firing times by inspecting the OS scheduler. On macOS, parses `launchctl print gui/<uid>/com.compendium.curate`. On Linux, parses `systemctl --user list-timers compendium-curate.timer` and `systemctl --user status compendium-curate.service`.
- **A new `compendium/schedule/` module** with the generator + install/uninstall + status code paths. The generator is shaped to host additional `target` verbs in later phases (Phase 4 inbox watcher, possibly a curate target rename for backup). For Phase 3, the only target is `curate`.
- **ADR-012 status update** in `docs/Compendium.md`: marks the ADR as shipped in v0.2 Phase 3 with a link to PR.
- **CLAUDE.md update**: the status section gains v0.2 Phase 3; the resolved-decisions paragraph names the launchd/systemd timer-fires-CLI as the v0.2 Phase 3 interim for scheduled curation (Phase 7's access-surface daemon may absorb it in a later refactor).
- **An operational document** `docs/operations/schedule.md` covering: what the scheduled unit does and does not do; the install / uninstall / status workflow; the macOS Full Disk Access caveat for vault paths under protected directories; an "observed firing" walkthrough (the smoke recipe); a retention note about the log file under `~/Library/Logs/compendium/` (macOS) / journalctl (Linux).
- **A Phase 3 (v0.2) smoke section** appended to `tests/manual/smoke_test.md`.
- **Tests.** A new `tests/test_schedule.py` mirrors the shape of `tests/test_backup.py`: unit tests for cadence parsing, plist XML / systemd unit content, idempotent uninstall, missing-platform guard. An `integration`-marked end-to-end test installs the schedule on the current host with a short cadence, force-kicks the unit via the OS scheduler, observes a new `graph_analysis_runs` row in PostgreSQL, then uninstalls.

## Capabilities

### New Capabilities

- `scheduled-curation`: the `compendium schedule install` / `uninstall` / `status` CLI surface, the per-OS unit generators in `compendium/schedule/`, the operational doc `docs/operations/schedule.md`, and the integration test that verifies a kicked unit writes a `graph_analysis_runs` row without manual `compendium curate run` invocation.

### Modified Capabilities

<!-- None. The existing curation module (`compendium/curate/`) and its
`graph_curation_signals` / `graph_analysis_runs` tables are unchanged.
Phase 3 wraps the existing `compendium curate run` invocation in an
OS-scheduler envelope; nothing about the curation slow loop's behaviour
or contract changes. -->

## Impact

- **New code/files:** `compendium/schedule/__init__.py`, `compendium/schedule/install.py`, `compendium/schedule/status.py`, `compendium/schedule/cadence.py`; new CLI verbs `schedule install` / `uninstall` / `status` in `compendium/__main__.py`; `tests/test_schedule.py`; `docs/operations/schedule.md`.
- **Modified files:** `tests/manual/smoke_test.md` (new § Phase 3 (v0.2)); `README.md` (one-line pointer); `CLAUDE.md` (v0.2 Phase 3 status + resolved decision); `docs/Compendium.md` (ADR-012 status: Accepted (v0.2 Phase 3 shipped 2026-MM-DD)).
- **No schema migration.** Reads existing `graph_analysis_runs` / `graph_curation_signals` tables.
- **No new runtime dependency.** `launchctl` (macOS) and `systemctl` (Linux) are OS-native; both ship by default. The schedule helpers shell out to them, like the Phase 2 backup install does.
- **No CI change.** The integration test is `integration`-marked and skips when the local OS scheduler is not available; CI's Linux runners have `systemctl --user` available but force-kicking a user timer in a CI environment is brittle — the test design uses `systemctl --user start <unit>.service` directly (the manual-kick path) so CI is not required to wait for a timer fire.
- **Schedule installer is target-extensible but Phase 3 ships one target.** The `target` parameter accepts `curate` only in this phase. A future phase can add `inbox` (Phase 4) or refactor `compendium backup install` to use the same surface.
- **Out of scope:**
  - **Refactoring `compendium backup install`** to use the new generic scheduler. Phase 2's installer keeps its own code path in v0.2; a v0.3 phase can factor out the shared bits.
  - **System-level (root) units.** Schedule install writes user-level units only (`~/Library/LaunchAgents/`, `~/.config/systemd/user/`). System-level units require sudo and are out of charter.
  - **A long-running daemon process** that hosts the slow loop in-process. ADR-012's long-term home for scheduled curation is Phase 7's access-surface daemon; Phase 3 ships the launchd/systemd timer interim that does the same job at a coarser granularity.
  - **Sub-minute cadences.** Minimum granularity is one minute (matches systemd timer's `OnUnitActiveSec` resolution). The slow loop is meant to run on the order of hours, not seconds.
  - **Cadence configuration in `settings.yaml`.** Cadence is set at install time via `--every`; changing it means uninstalling and reinstalling. No mid-runtime cadence change.
  - **A "run once now and exit" admin verb.** The existing `compendium curate run` already does that.
