## ADDED Requirements

### Requirement: A single `service_unit` seam installs, uninstalls, and reports status for OS-managed units

The system SHALL provide a `compendium/service_unit/` module exposing `install(descriptor)`, `uninstall(descriptor)`, and `status(descriptor)` over a `UnitDescriptor` value object, with exactly two adapters behind a single platform dispatch: a launchd adapter for macOS and a systemd user-unit adapter for Linux. Platform detection SHALL occur in exactly one place; an unsupported platform SHALL raise `ServiceUnitError(step="platform", …)`. All four Compendium services (`backup`, `curate`, `inbox`, `serve`) SHALL install, uninstall, and report status through this seam.

#### Scenario: macOS install renders and loads a LaunchAgent

- **GIVEN** a `UnitDescriptor` on a darwin platform
- **WHEN** `install(descriptor)` runs
- **THEN** a plist is written to `~/Library/LaunchAgents/<label>.plist` and loaded via `launchctl bootout` (best-effort) then `launchctl bootstrap`, and a non-zero `bootstrap` raises `ServiceUnitError`

#### Scenario: Linux install renders and enables a systemd user unit

- **GIVEN** a `UnitDescriptor` on a linux platform
- **WHEN** `install(descriptor)` runs
- **THEN** the unit file(s) are written under `~/.config/systemd/user/`, `systemctl --user daemon-reload` runs, the unit is enabled with `systemctl --user enable --now`, and a non-zero enable raises `ServiceUnitError`

#### Scenario: An unsupported platform is rejected in one place

- **GIVEN** a platform that is neither darwin nor linux
- **WHEN** any of `install` / `uninstall` / `status` runs
- **THEN** `ServiceUnitError(step="platform", …)` is raised, and no other module performs its own platform check

### Requirement: The `Trigger` taxonomy is the only axis that varies between services

`UnitDescriptor` SHALL carry a `Trigger` from a closed set: `Interval(seconds)`, `Calendar(hour, minute)`, `WatchPaths(paths)`, `AlwaysOn()`. The adapter SHALL derive the unit type from the trigger — `Interval`/`Calendar` produce a timer + service, `WatchPaths` produces a path + service, `AlwaysOn` produces a service only — and render the platform-specific keys for that trigger.

#### Scenario: Interval trigger renders interval keys

- **WHEN** an `Interval(seconds=N)` descriptor is rendered
- **THEN** macOS uses `StartInterval=N` and Linux uses a `.timer` with `OnUnitActiveSec=N`, `OnBootSec=N`, and `Persistent=true`

#### Scenario: Calendar trigger renders wall-clock keys

- **WHEN** a `Calendar(hour=H, minute=M)` descriptor is rendered
- **THEN** macOS uses `StartCalendarInterval` with hour H and minute M, and Linux uses a `.timer` with `OnCalendar=*-*-* HH:MM:00`

#### Scenario: WatchPaths trigger renders a path watcher

- **WHEN** a `WatchPaths(paths=[…])` descriptor is rendered
- **THEN** macOS uses a `WatchPaths` array with one entry per path, and Linux uses a `.path` unit with one `PathChanged=` per path paired with a `.service`

#### Scenario: AlwaysOn trigger renders a kept-alive daemon

- **WHEN** an `AlwaysOn()` descriptor is rendered
- **THEN** macOS uses `RunAtLoad=true` + `KeepAlive=true`, and Linux uses a `.service` with `Restart=always` enabled into `default.target`

### Requirement: Migration to the seam preserves behaviour exactly

The four services SHALL keep their current labels, unit-file paths, generated unit content, idempotency, CLI verbs, exit codes, and rendered (`text` and `json`) output. The migration SHALL change only where the lifecycle is implemented, not what it produces.

#### Scenario: Labels and paths are unchanged

- **WHEN** each service builds its descriptor
- **THEN** the labels remain `com.compendium.{backup,curate,inbox,serve}`, the Linux basenames remain `compendium-{backup,curate,inbox,serve}`, and the plist / unit file paths are identical to the pre-migration locations

#### Scenario: Generated unit content is byte-identical

- **GIVEN** golden fixtures captured from the four modules before migration
- **WHEN** the adapters render each service's unit on each platform
- **THEN** the rendered plist / systemd unit text matches the captured golden output

#### Scenario: Uninstall stays idempotent

- **WHEN** `uninstall(descriptor)` runs against an already-absent unit
- **THEN** it succeeds and reports "not installed" (or the service's existing equivalent), as before

### Requirement: One error type and one status type replace the per-service copies

The system SHALL provide a single `ServiceUnitError(step, detail)` and a single `UnitStatus` (with optional trigger-specific fields and a `to_dict()`), used by all four services. The previous step vocabularies SHALL be preserved as `step` values so log and error detail are unchanged. The subprocess calls SHALL go through an injectable `Runner` so the lifecycle is testable without a real scheduler.

#### Scenario: A failed lifecycle command raises the shared error with a preserved step

- **GIVEN** an injected `Runner` that returns a non-zero exit for `launchctl bootstrap`
- **WHEN** `install(descriptor)` runs
- **THEN** `ServiceUnitError(step="launchctl_bootstrap", detail=<stderr>)` is raised

#### Scenario: Status parses the scheduler CLI into one shape

- **GIVEN** an injected `Runner` returning canned `launchctl print` / `systemctl` output
- **WHEN** `status(descriptor)` runs
- **THEN** a single `UnitStatus` is returned whose `to_dict()` yields the JSON each service's status verb already prints

#### Scenario: The lifecycle is unit-tested without a scheduler

- **WHEN** the `service_unit` tests run in CI
- **THEN** no real `launchctl` or `systemctl` is invoked; the `Runner` is faked and the rendered units are asserted against golden strings
