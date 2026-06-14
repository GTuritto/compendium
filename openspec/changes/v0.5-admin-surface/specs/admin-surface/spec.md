# Spec — v0.5: admin / ops surface in the TUI and WebUI (ADR-020)

## ADDED Requirements

### Requirement: Destructive ops never reach the no-auth surface
Destructive operations (source delete, any wipe, `restore`) and system-unit
management (schedule/inbox/serve/backup install/uninstall) SHALL NOT be exposed
on the WebUI, HTTP, or MCP. They SHALL be available only on the CLI and TUI.

#### Scenario: WebUI excludes destructive ops
- **WHEN** the WebUI is inspected
- **THEN** it offers no delete, wipe, restore, or unit-install control

### Requirement: The TUI exposes the full admin surface
The TUI SHALL be able to run reindex, graph rebuild, backup, source delete
(behind an explicit confirmation), and report/control the schedule, inbox, and
serve units.

#### Scenario: TUI admin actions
- **WHEN** the curator opens the admin actions in the TUI
- **THEN** reindex, graph rebuild, backup, and a confirmed source delete are
  available and report their result

### Requirement: The WebUI exposes a dashboard and non-destructive ops
The WebUI SHALL gain a dashboard (store/index counts and health) and the
non-destructive operations: `reindex`, `graph rebuild`, `backup` (export), and
trace/browse inspection.

#### Scenario: WebUI dashboard + safe ops
- **WHEN** a user opens the WebUI dashboard
- **THEN** it shows counts/health and offers reindex / graph rebuild / backup,
  each reporting success or failure

### Requirement: UIs are thin callers of one operations seam
Both UIs SHALL invoke the same operation entry points the CLI uses; no admin
operation logic SHALL be duplicated inside a UI.

#### Scenario: shared seam
- **WHEN** reindex is triggered from the CLI, the TUI, and the WebUI
- **THEN** all three call the same underlying operation, not three copies
