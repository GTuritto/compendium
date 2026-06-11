# Spec — status readers through the probe seam

## ADDED Requirements

### Requirement: The seam owns all scheduler-CLI interaction
`compendium/schedule/status.py` and `compendium/api/service.py` SHALL contain
no `subprocess` call and no `sys.platform` dispatch; they consume
`service_unit.probe` / `service_unit.probe_activity`.

#### Scenario: greps prove the routing
- **WHEN** `grep -n "subprocess\|sys.platform"` runs over the two readers
- **THEN** there are no matches

### Requirement: An activity probe for rich status fields
`probe_activity(descriptor)` SHALL return a `Probe` whose stdout carries the
scheduler's activity output (macOS `launchctl print`; Linux `systemctl --user
status` + `list-timers` for triggered units), via the injectable `Runner`.

#### Scenario: readers parse recorded output
- **WHEN** a fake Runner returns captured scheduler-CLI output
- **THEN** both readers produce the same status fields as on a real host
