# Tasks — v0.5-source-hard-delete

Gated on: the v0.4 verdict (page-arm advantage) per `docs/proposals/README.md`.
Build-ready spec only until then.

- [ ] 1a delete orchestration: `delete_source(source_id)` in `repository.py`
  over the existing `delete_*` primitives — canonical-first (source page row +
  vault file, then `sources` cascade, then `semantic_edges`, then OpenSearch /
  Qdrant / Memgraph entries, then `index_sync_state`); idempotent;
  transactional on the PostgreSQL side; unit + integration tests incl. the
  partial-derived-failure + reconcile path. ADR-018 inline in
  `docs/Compendium.md`.
- [ ] 1b CLI verb: `compendium source delete <id|slug> [--dry-run] [--force]`
  — slug or id resolution, `--dry-run` impact summary (counts + concepts left
  thinly grounded), confirmation on the destructive path.
- [ ] 1c TUI action: a delete action on the sources screen behind an explicit
  confirm, reusing the orchestration; headless Pilot test.
- [ ] 1d dangling-concept signal: confirm/extend the slow loop so a concept
  left thinly grounded by a delete is surfaced (ADR-009); test.
- [ ] 1e docs + close: `docs/operations/delete.md`; CHANGELOG; smoke section
  appended (`source delete --dry-run` then a real delete, then a query that no
  longer returns it); full fast + golden green; version bump in the completion
  commit.
