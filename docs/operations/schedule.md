# Scheduled curation

Operational reference for `compendium schedule install`,
`compendium schedule uninstall`, and `compendium schedule status` —
the v0.2 Phase 3 mechanism that fires the curation slow loop on a
schedule under launchd (macOS) or a systemd user timer (Linux).

## What the scheduled unit does

The scheduled unit invokes `compendium curate run` on the configured
cadence. Each firing:

- writes one row to `graph_analysis_runs`;
- inserts new `graph_curation_signals` for low-coverage queries,
  dangling concepts, thin grounding, and contradictions found in
  the corpus state;
- moves any auto-extracted edges into `graph_extracted_edges` (the
  Phase 8 generator, when shipped);
- exits.

It does **not** synthesize pages, promote drafts, or write to the
vault. Curation is signal-generating only; the curator drains the
signals manually via `compendium curate list` / `synth` or the TUI.

## What the scheduled unit does **not** do

- It is not a daemon. Each firing is a CLI invocation that exits.
- It does not host the access surface. That lands with Phase 7's
  `compendium serve`.
- It does not check whether Compendium's stores are reachable
  before firing. A firing against a stopped stack records the
  failure to the log file and exits non-zero; nothing else
  happens. Curate's existing error handling applies.

## Configuration

The cadence is set at install time via `--every`:

```sh
uv run python -m compendium schedule install                # default --every 1h
uv run python -m compendium schedule install --every 30m
uv run python -m compendium schedule install --every 2h30m
```

Accepted forms: `Nh`, `Nm`, `NhMm`. Minimum granularity is one
minute; maximum is seven days. There is no `settings.yaml` cadence
override in v0.2 Phase 3 — changing cadence means
`schedule uninstall` then `schedule install --every <new>`.

## Daily workflow

```sh
uv run python -m compendium schedule install               # default 1h cadence
uv run python -m compendium schedule status                # confirm loaded
uv run python -m compendium schedule status --format json  # machine-readable
uv run python -m compendium schedule uninstall             # remove
```

The install command emits a structlog event per step (plist written,
loaded) and prints a one-line `schedule install: <path> (<detail>)`
to stdout. The uninstall command is idempotent — re-running after the
unit is gone reports "not installed" and exits 0.

## How firings work

### macOS (LaunchAgent)

The unit lives at `~/Library/LaunchAgents/com.compendium.curate.plist`
with `StartInterval=<seconds>`. launchd fires the unit every
`<seconds>` of *active time* (the interval clock pauses while the
host is asleep). After a long sleep, the unit fires once on wake
and resumes the interval cadence.

Logs:

- stdout → `~/Library/Logs/compendium/curate.out.log`
- stderr → `~/Library/Logs/compendium/curate.err.log`

### Linux (systemd user timer)

The unit lives at `~/.config/systemd/user/compendium-curate.timer`
with `OnUnitActiveSec=<seconds>` and `Persistent=true`. The service
runs `compendium curate run` per fire. `Persistent=true` catches up
a missed fire on the next user session (the unit fires once on
session start if the cadence elapsed during a host-off period).

Logs:

```sh
journalctl --user -u compendium-curate.service
```

## macOS Full Disk Access

If the vault or the backing-store data lives under a macOS-protected
directory (Documents, Desktop, iCloud Drive), launchd may refuse to
read or write those paths. Grant Terminal (or `uv` / `python`) "Full
Disk Access" in **System Settings → Privacy & Security → Full Disk
Access**. The scheduled run will otherwise emit I/O errors visible in
`~/Library/Logs/compendium/curate.err.log`.

The same caveat applies to Phase 2's backup unit. If both are
installed and only one shows errors, check which paths each unit
touches (the curate unit reads PostgreSQL + the vault but does not
write the vault).

## Triggering a fire manually

For verification or one-off catch-up, kick the OS scheduler
directly:

```sh
# macOS
launchctl kickstart -k gui/$(id -u)/com.compendium.curate

# Linux
systemctl --user start compendium-curate.service
```

Each kick produces one new `graph_analysis_runs` row, same as a
natural fire. The smoke walk uses this path to avoid waiting on the
natural cadence.

## Uninstalling on host migration

Before retiring a host or switching primary, remove the scheduled
units so they do not race with the new host:

```sh
uv run python -m compendium schedule uninstall
uv run python -m compendium backup uninstall
```

Both are idempotent; running them on a clean host exits 0 with "not
installed".

## Why the timer remains

The access-surface daemon has shipped, but scheduled curation still uses the
launchd/systemd timer. v0.4 explicitly defers absorbing the slow loop into the
daemon until real-corpus operation demonstrates cadence or crash-recovery
pressure. Revisit only when runs overlap, fall behind, or miss material that the
daily ask habit needs.
