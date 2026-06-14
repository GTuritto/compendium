# Admin / ops surface (TUI + WebUI)

The admin operations are reachable from the UIs, split by **posture** (ADR-020):

- **TUI** (local, over SSH) — the full set, including destructive ops.
- **WebUI** (no-auth, LAN) — a dashboard and **non-destructive ops only**.

Both UIs are thin callers of the same functions the CLI uses (one operations
seam, `compendium/tui/data.py`); no admin logic is duplicated in a UI.

## TUI

`compendium tui`, then:

| Screen | Key | Action |
| --- | --- | --- |
| Dashboard | `R` | Reindex all (rebuild derived indexes) |
| Dashboard | `G` | Rebuild graph (Memgraph from canonical) |
| Dashboard | `I` | Process inbox now (drain stuck files) |
| Sources | `D` | **Delete** the selected source (typed `DELETE` confirmation) |
| Sources | `i` | Ingest a source |

(Admin ops use capital keys to avoid the lowercase global navigation bindings
`d`/`s`/`p`/`w`/`c`/`g`.)

Delete is destructive (ADR-018): it removes the source and everything derived,
behind a typed confirmation. It is TUI/CLI only.

## WebUI

`compendium web`, then the **Dashboard** view:

- Store/index counts, health, and sync lag.
- **Reindex all**, **Rebuild graph**, **Process inbox now** — non-destructive;
  they rebuild/recover from the canonical layer (ADR-001), so they cannot lose
  data.

The WebUI deliberately has **no** delete / wipe / restore / unit-install
control. Those stay TUI/CLI only because the WebUI is no-auth and LAN-exposed
(ADR-020). A source-level test enforces this.

## Inbox recovery + the safety-net sweep

The inbox watcher is edge-triggered and can miss files dropped as a batch or
mid-copy. Two backstops:

- **Manual:** "Process inbox now" (TUI `I` on the dashboard, or the WebUI
  button), equivalently `compendium inbox process`.
- **Automatic:** a periodic sweep — a systemd user timer
  (`compendium-inbox-sweep.timer`) firing `compendium inbox process` every ~10
  minutes; a no-op when the inbox is empty. Installed on the deployment host.

## The operations seam

CLI, TUI, and WebUI all call the same underlying functions — `sync.reindex`,
`graph.rebuild`, `inbox.process`, `maintenance.delete_source` — through the
`tui/data.py` provider. Exposing a new operation is done once; the posture rule
(destructive ops never on the no-auth surface) is enforced by tests.
