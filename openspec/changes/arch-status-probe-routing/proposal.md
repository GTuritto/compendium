## Why

`service_unit.probe()` exists precisely for status readers (injectable
`Runner`, raw scheduler-CLI output per its docstring) and has zero callers
beyond `inbox/install.py`. Both rich status readers bypass it:
`schedule/status.py` dispatches on `sys.platform` itself and runs
`launchctl print` / two `systemctl` commands directly (lines 50, 85-86,
137-161); `api/service.py` repeats the dance (139, 152-153, 162-164). Neither
is testable without monkeypatching `subprocess` — the gap the CI work exposed.

## What Changes

- **The seam grows an activity probe**: `service_unit.probe_activity(descriptor)`
  — macOS reuses `launchctl print` (the same output `probe` already returns);
  Linux runs `systemctl --user status <unit>` plus, for triggered units,
  `list-timers --all <unit>`, concatenated into `Probe.stdout`.
- **Both readers consume `Probe`**: `schedule.read_status()` and the serve
  `read_status()` take an optional `runner` and parse `Probe.stdout`; their
  field-extraction regexes and `_parse_host_port` stay per-service (the seam's
  documented split). All `subprocess` and `sys.platform` code in the two
  readers is deleted.
- **Reader tests become recorded-output tests**: fake `Runner`s with captured
  launchctl/systemctl output drive both readers on any host, including CI.

## Impact

- Affected: `service_unit/{__init__,systemd}.py`, `schedule/status.py`,
  `api/service.py`, `tests/test_schedule.py`, `tests/test_serve_service.py`,
  `tests/test_service_unit.py`.
- Behaviour-preserving: status output field-for-field identical on the
  primary host.
