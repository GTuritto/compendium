# Tasks — v0.5-admin-surface

Gated on: the v0.4 verdict per `docs/proposals/README.md`. Build-ready spec
only. Depends on v0.5-source-hard-delete for the TUI delete action.

- [ ] 1a operations seam: ensure one callable entry per admin op (reindex,
  graph rebuild, backup) that the CLI, TUI, and WebUI all use; ADR-020 inline
  in `docs/Compendium.md`.
- [ ] 1b TUI admin: actions for reindex / graph rebuild / backup, source delete
  (confirmed), and schedule/inbox/serve status+control; Pilot tests.
- [ ] 1c WebUI dashboard: counts/health view (parity with the TUI dashboard).
- [ ] 1d WebUI safe ops: reindex / graph rebuild / backup controls; explicit
  exclusion of delete/wipe/restore/unit-install; headless tests asserting the
  destructive ops are absent.
- [ ] 1e docs + close: `docs/operations/admin-surface.md`; CHANGELOG; smoke
  section; full fast + golden green; version bump in the completion commit.
