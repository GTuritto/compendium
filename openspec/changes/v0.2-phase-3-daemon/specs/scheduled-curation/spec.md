## ADDED Requirements

### Requirement: `compendium schedule install` writes a per-OS scheduled unit

The system SHALL provide a `compendium schedule install [--every <interval>]` CLI command that writes a user-level OS scheduler unit firing `compendium curate run` on the configured cadence. On macOS the unit SHALL be `~/Library/LaunchAgents/com.compendium.curate.plist` with `StartInterval=<seconds>`, loaded via `launchctl bootstrap gui/<uid>`. On Linux the unit SHALL be the pair `~/.config/systemd/user/compendium-curate.{service,timer}` with `OnUnitActiveSec=<seconds>` and `Persistent=true`, enabled via `systemctl --user enable --now`. When `--every` is omitted, the cadence SHALL default to `1h`.

#### Scenario: macOS install writes a LaunchAgent and registers it

- **WHEN** `compendium schedule install --every 1h` runs on macOS
- **THEN** `~/Library/LaunchAgents/com.compendium.curate.plist` exists with `StartInterval=3600`; `launchctl print gui/<uid>/com.compendium.curate` succeeds; the command exits 0

#### Scenario: Linux install writes a systemd user timer and enables it

- **WHEN** `compendium schedule install --every 1h` runs on Linux
- **THEN** `~/.config/systemd/user/compendium-curate.timer` and `compendium-curate.service` exist; the timer's `OnUnitActiveSec=3600`; `systemctl --user is-enabled compendium-curate.timer` reports `enabled`; the command exits 0

#### Scenario: Default cadence resolves to `1h`

- **WHEN** `compendium schedule install` runs with no `--every` flag
- **THEN** the resulting unit's interval is 3600 seconds

### Requirement: Cadence parsing accepts `Nh`, `Nm`, `NhMm`

The `--every` flag SHALL accept human-readable interval strings of the form `Nh` (hours), `Nm` (minutes), or `NhMm` (hours plus minutes). Sub-minute cadences SHALL be rejected. Cadences over 7 days SHALL be rejected. Malformed input SHALL produce a `ScheduleError` and a non-zero exit.

#### Scenario: Valid cadences parse to total seconds

- **WHEN** the cadence parser receives `1h`, `30m`, `2h30m`, `60m`
- **THEN** it returns `3600`, `1800`, `9000`, `3600` respectively

#### Scenario: Invalid cadences are rejected

- **WHEN** the cadence parser receives `0`, `30s`, `8d`, `abc`, or an empty string
- **THEN** it raises `ScheduleError`

### Requirement: `compendium schedule uninstall` is idempotent

The system SHALL provide a `compendium schedule uninstall` CLI command that unloads and removes the scheduled unit. The command SHALL be idempotent: when nothing is installed, it SHALL exit 0 and report "not installed".

#### Scenario: First uninstall removes the unit

- **GIVEN** the unit is installed
- **WHEN** `compendium schedule uninstall` runs
- **THEN** the unit file is removed; the OS scheduler no longer lists the unit; the command exits 0

#### Scenario: Repeat uninstall is a no-op

- **GIVEN** the unit is already gone
- **WHEN** `compendium schedule uninstall` runs
- **THEN** the command exits 0 with a "not installed" message; no error

### Requirement: `compendium schedule status` reports the unit's state

The system SHALL provide a `compendium schedule status` CLI command that reports whether the scheduled unit is loaded and, when available, the last firing time and the next firing time. Fields the OS scheduler does not provide (for example, a never-fired unit's `last_fired`) SHALL be reported as "unknown". The command SHALL exit 0 when the unit is loaded and 1 when it is not.

#### Scenario: A loaded unit reports loaded + next-fire

- **GIVEN** the unit is installed and has not yet fired
- **WHEN** `compendium schedule status` runs
- **THEN** the output names the unit as loaded; `last_fired` is "unknown" (or absent); `next_fire` is populated; the command exits 0

#### Scenario: An absent unit reports not-installed

- **WHEN** `compendium schedule status` runs and no unit has been installed
- **THEN** the output reports "not installed"; the command exits 1

### Requirement: Scheduled fires invoke `compendium curate run` and write a `graph_analysis_runs` row

Each firing of the scheduled unit SHALL invoke `compendium curate run` end-to-end against the configured PostgreSQL and write one row to `graph_analysis_runs` (the existing v0.1 Phase 9 contract). The schedule itself SHALL NOT modify the curation contract — it only triggers the existing CLI verb.

#### Scenario: A manual kick produces one new `graph_analysis_runs` row

- **GIVEN** the scheduled unit is installed
- **WHEN** the OS scheduler is manually kicked (`launchctl kickstart` on macOS; `systemctl --user start` on Linux)
- **THEN** within 30 seconds, `graph_analysis_runs` contains exactly one new row

### Requirement: The scheduled unit survives a host reboot

The scheduled unit SHALL be installed in a way that survives a host reboot. On macOS this is implicit (LaunchAgent loaded into the user's launch domain persists across reboot). On Linux this is achieved via `systemctl --user enable` (the timer is auto-enabled on next user session) together with `Persistent=true` (missed fires catch up on the next session).

#### Scenario: Survival check on macOS

- **GIVEN** the unit is installed
- **WHEN** the host reboots
- **THEN** `launchctl print gui/<uid>/com.compendium.curate` continues to succeed after login; no manual reinstall is required

#### Scenario: Survival check on Linux

- **GIVEN** the unit is installed
- **WHEN** the host reboots
- **THEN** after the next `systemctl --user` session, `compendium-curate.timer` is `enabled` and `active`

### Requirement: ADR-012 status reflects Phase 3 ship

`docs/Compendium.md` ADR-012 SHALL be updated to reflect that Phase 3 has shipped the timer-fires-CLI mechanism as the v0.2 interim, with a clarifying paragraph in the "Alternatives considered" section explaining that the long-term home for scheduled curation is Phase 7's access-surface daemon.

#### Scenario: ADR-012 status text is updated post-merge

- **WHEN** the curator reads ADR-012 after Phase 3 merges
- **THEN** the status line reads `Accepted (v0.2 Phase 3, shipped <date> via PR #<n>)` and the alternatives section names the timer-fires-CLI as the interim, with Phase 7 absorbing later

### Requirement: Operational document and smoke section

The repository SHALL include `docs/operations/schedule.md` covering: what the scheduled unit does and does not do; install / status / uninstall workflows; macOS Full Disk Access caveat; where the fire logs land; how to trigger a fire manually; how to uninstall on host migration; the v0.2 interim posture. `tests/manual/smoke_test.md` SHALL include a Phase 3 (v0.2) section covering: install at the default cadence; install at a custom cadence; status of a loaded unit; manual-kick produces a `graph_analysis_runs` row; uninstall + idempotent re-uninstall.

#### Scenario: The operational doc covers the required sections

- **WHEN** the curator reads `docs/operations/schedule.md` after Phase 3 merges
- **THEN** the document explains the install/status/uninstall workflows, the manual-kick recipe, the FDA caveat, and the v0.2 interim posture

#### Scenario: The smoke walk exercises the full install/fire/uninstall cycle

- **WHEN** the operator walks the Phase 3 (v0.2) smoke section
- **THEN** they install the unit, see its status, kick it, observe a `graph_analysis_runs` row, then uninstall cleanly
