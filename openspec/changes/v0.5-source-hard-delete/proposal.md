# Proposal — v0.5: hard delete of sources

## Why

Compendium can ingest and re-ingest but it cannot remove. A mis-ingest — a
wrong file, a bad parse, the deployment smoke note — stays in the corpus
permanently, polluting retrieval and, during v0.4, the very A/B that measures
the core bet. Hard delete of a source closes that one-way door. This change
formalizes the requirement so it is build-ready; it stays **parked behind the
v0.4 verdict** (`docs/proposals/README.md`), and the design was fixed by the
2026-06-14 scoping: hard delete (purge), scoped to a source.

## What Changes

- **A delete orchestration (ships ADR-018).** `delete_source(source_id)`
  removes a source and everything derived, **canonical-first**: the source
  page (its vault markdown file plus the `wiki_pages` row — the
  `wiki_pages.source_id -> sources(id)` FK has **no** cascade, so the page is
  removed first), then the `sources` row (whose `ON DELETE CASCADE` clears
  `source_documents` and `chunks`), then the `semantic_edges` rows
  (system-of-record since ADR-013) referencing the source or its chunks, then
  the derived-index entries via the existing primitives (`delete_document` /
  OpenSearch, `delete_point` / Qdrant, Memgraph node+edge removal), then the
  `index_sync_state` rows.
- **CLI verb.** `compendium source delete <id|slug> [--dry-run] [--force]`.
  `--dry-run` reports what would be removed (chunk/page/index counts and any
  concept pages that would be left thinly grounded) and removes nothing.
- **TUI action.** A delete action on the sources screen, behind an explicit
  confirmation.
- **Not on the network surface.** Delete is destructive, so it is CLI/TUI
  only and is never added to the facade, HTTP, or MCP (ADR-011, refined by
  the admin-surface decision ADR-020).
- **Fallout is curated, not cascaded.** A concept page grounded on the deleted
  source is **not** auto-deleted; the slow loop (ADR-009) surfaces it as a
  thin-grounding / dangling-concept signal. "Synthesis is curator-driven"
  stays intact.
- **Self-reconciling.** Canonical leads; if a derived-index delete fails, the
  canonical row is already gone and `reindex` + `graph rebuild` reconcile
  (derived stores rebuild from the canonical layer per ADR-001).

## Impact

New: a `delete_source` orchestration (in `compendium/db/repository.py` over
the existing `delete_*` primitives, plus Memgraph node removal); the `source
delete` CLI verb in `__main__.py`; a TUI sources-screen delete action; ADR-018
inline in `docs/Compendium.md`; `docs/operations/delete.md`;
`tests/test_delete.py`. Modified: `__main__.py`, the TUI sources screen,
`repository.py`, CHANGELOG, smoke playbook. **No schema migration** (reuses
the existing `ON DELETE CASCADE` and index-delete primitives). Version bump
per the +1-patch-per-phase policy.

## Gates

Parked behind the v0.4 verdict: implementation starts only after v0.4 Phase 1
returns a page-arm advantage (`docs/proposals/README.md`). Until then this is
a build-ready spec only. (An immediate one-off removal of a single polluting
source — e.g. the smoke note — does not need this feature; it can be done with
the existing primitives, separately from this phase.)
