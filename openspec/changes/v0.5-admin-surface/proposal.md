# Proposal — v0.5: admin / ops surface in the TUI and WebUI

## Why

The admin and ops verbs (reindex, graph rebuild, backup, schedule, inbox,
serve, and the new source delete) live almost entirely on the CLI. The TUI and
WebUI cannot drive them, so day-to-day operation means SSH + CLI. This change
brings the admin surface into the UIs, split by security posture. Parked behind
the v0.4 verdict (`docs/proposals/README.md` §2). Design fixed 2026-06-14:
**TUI = full (incl. destructive); WebUI = safe-only.**

## What Changes

- **Ships ADR-020** — a posture rule that refines ADR-011: destructive
  operations (data loss) and system-unit management never appear on the no-auth
  network surface; non-destructive ops earn a read-mostly WebUI home.
- **TUI (full).** The TUI gains the admin actions it lacks: reindex / graph
  rebuild, backup, source delete (behind confirmation, from the delete change),
  and visibility/control of the schedule/inbox/serve units. The TUI is local
  over SSH, so destructive actions are allowed.
- **WebUI (safe-only).** The WebUI gains a **dashboard** (the counts/health the
  TUI dashboard shows) and non-destructive ops: `reindex` and `graph rebuild`
  (they rebuild derived stores from the canonical layer — no data loss),
  `backup` (export), trace inspection, and browse. It does **not** get source
  delete, any wipe, `restore`, or unit install/uninstall.
- **One operations seam.** Both UIs call the same operation functions the CLI
  uses (no logic duplicated in a UI); the UIs are thin callers, consistent with
  the facade/provider pattern already in place.
- **Inbox recovery + self-healing.** A "process inbox now" action (TUI + WebUI,
  non-destructive) plus a periodic safety-net sweep, because the edge-triggered
  `.path` watcher silently misses files dropped as a batch or mid-SMB-copy. The
  sweep (a timer running `inbox process`) is the root-cause fix and is a no-op on
  an empty inbox; it can ship ahead of this change as pure deployment config (a
  systemd timer), since it is not product code.

## Impact

New: a WebUI dashboard view + WebUI admin (safe) controls; TUI admin actions;
ADR-020 inline in `docs/Compendium.md`; `docs/operations/admin-surface.md`;
tests (TUI Pilot + WebUI headless). Modified: the TUI screens, the WebUI app,
possibly a thin ops-callable module so both UIs and the CLI share one entry per
operation, CHANGELOG, smoke playbook. **No schema migration.** Version bump per
policy.

## Gates

Parked behind the v0.4 verdict. Build-ready spec only. Depends on the
source-delete change (item 1) for the TUI delete action; reindex/graph
rebuild/backup already exist as CLI verbs to wrap.
