# Tasks — v0.2-phase-3-daemon

Implements v0.2 Phase 3 of `docs/COMPENDIUM_V0.2_BUILD.md`. Ships ADR-012. No schema migration; no new runtime dependency. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. `compendium schedule install` / `uninstall` (3a)

- [ ] 1.1 `compendium/schedule/__init__.py`: module surface re-exporting the public verbs.
- [ ] 1.2 `compendium/schedule/cadence.py`: `parse_interval(value: str) -> int` that accepts `Nh`, `Nm`, `NhMm`; returns total seconds; rejects sub-minute (`< 60s`) and over-week (`> 604800s`); rejects malformed input with a clean `ScheduleError`.
- [ ] 1.3 `compendium/schedule/install.py`: platform detect (darwin / linux only); macOS branch writes `~/Library/LaunchAgents/com.compendium.curate.plist` with `StartInterval=<seconds>`; Linux branch writes `~/.config/systemd/user/compendium-curate.{service,timer}` with `OnUnitActiveSec=<seconds>` and `Persistent=true`; both branches invoke `uv run --project <repo> python -m compendium curate run`; macOS branch loads via `launchctl bootstrap`, Linux branch enables via `systemctl --user enable --now`.
- [ ] 1.4 `compendium schedule install [--every <interval>]` CLI verb. Defaults `--every` to `1h`. Prints the resolved unit path and the loader exit code.
- [ ] 1.5 `compendium schedule uninstall` CLI verb. Unloads then removes the unit; idempotent (no error when nothing is installed).
- [ ] 1.6 Unit tests for cadence parsing (valid / invalid), plist XML contains `StartInterval` for the right cadence, systemd timer unit contains `OnUnitActiveSec` for the right cadence, platform-detect refuses non-supported `sys.platform`.

## 2. `compendium schedule status` (3b)

- [ ] 2.1 `compendium/schedule/status.py`: `read_status()` returns a `ScheduleStatus` with fields `loaded: bool`, `last_fired: datetime | None`, `next_fire: datetime | None`, `unit_path: Path`.
- [ ] 2.2 macOS implementation: runs `launchctl print gui/<uid>/com.compendium.curate`, parses the human-readable output for `state` / `last exit` / `next launch` fields. Tolerates missing fields with `None`.
- [ ] 2.3 Linux implementation: runs `systemctl --user list-timers --all compendium-curate.timer` and `systemctl --user status compendium-curate.service`; parses for `LAST`, `NEXT`, `Active`. Tolerates missing fields.
- [ ] 2.4 `compendium schedule status` CLI verb. Exits 0 when the unit is loaded; exits 1 with "not installed" when it is not. Prints a small text block (or JSON via `--format json`).
- [ ] 2.5 Unit tests with stubbed `subprocess.run` returns: a loaded unit, a never-fired unit, a not-installed unit.

## 3. ADR-012 ship + CLAUDE.md update (3c)

- [ ] 3.1 `docs/Compendium.md` ADR-012: update `**Status:** Accepted (v0.2).` to `**Status:** Accepted (v0.2 Phase 3, shipped 2026-MM-DD via PR #<n>). Phase 3 ships the launchd/systemd timer-fires-CLI as the v0.2 interim; Phase 7 (or a later refactor) absorbs the schedule into the access-surface daemon.`
- [ ] 3.2 `docs/Compendium.md` ADR-012's "Alternatives considered" — leave the "User-owned scheduler invoking the CLI was rejected once the access surface entered scope" paragraph intact, but add a clarifying paragraph below it: "v0.2 Phase 3 ships this same approach as the interim because Phase 7's access-surface daemon does not exist yet; a later refactor will absorb the schedule."
- [ ] 3.3 `CLAUDE.md` status section: add a `v0.2 Phase 3 — Scheduled curation daemon` line under the v0.2 subsection with the merge date / PR number.
- [ ] 3.4 `CLAUDE.md` resolved decisions: add a line noting Phase 3's interim approach (timer-fires-CLI) and the planned Phase 7 absorption.

## 4. Operational doc + smoke + integration test + acceptance (3d)

- [ ] 4.1 `docs/operations/schedule.md`: sections — "What the scheduled unit does"; "Daily workflow (install / status / uninstall)"; "How firings work" (interval semantics, sleep behaviour, persistent catch-up); "macOS Full Disk Access" (mirror Phase 2's section); "Logs" (where stdout/stderr from each fire go); "Triggering a fire manually" (`launchctl kickstart` / `systemctl --user start`); "Uninstalling on host migration"; "Why this is an interim" (Phase 7 will absorb the schedule).
- [ ] 4.2 Append the Phase 3 (v0.2) section to `tests/manual/smoke_test.md` with scenarios v0.2-3.1 → v0.2-3.6.
- [ ] 4.3 `README.md`: add a one-line pointer in the v0.2 status sentence to `docs/operations/schedule.md`.
- [ ] 4.4 `tests/test_schedule.py`: integration test marked `integration`. Records the current `graph_analysis_runs` row count; runs `schedule install`; manually kicks the unit via the OS scheduler; waits up to 30 s for a new row; asserts the count increased by exactly one; runs `schedule uninstall`; verifies idempotent re-uninstall.
- [ ] 4.5 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 3: `compendium schedule install [--every 1h]` writes the OS-native unit and the unit fires `compendium curate run`; `compendium schedule uninstall` removes it; the loop survives a host reboot (implied by the OS scheduler's contract; smoke walk's natural-fire scenario covers the proof); `compendium schedule status` reports the unit's state and last/next firing; ADR-012 + CLAUDE.md updated; smoke walk passes.
- [ ] 4.6 `openspec validate v0.2-phase-3-daemon` clean.
