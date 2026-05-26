## Context

This change implements Phase 7 (query traces and revision tracking — operational telemetry, workstream I) of `docs/COMPENDIUM_BUILD.md`. It depends on Phase 5 (the `query_traces` writer and the `compendium/retrieve/pipeline.query` entry point) and builds on Phase 3 (`wiki_page_revisions`, the vault) and Phase 1 (`promotion_events`, the `page_status`/`promotion_kind`/`page_generator` enums). The commands and their semantics are specified in `docs/Compendium.md` ADR-007 and are implemented faithfully.

ADR-007 is the governing decision: every query is replayable and every page is diffable. Phase 7 turns the already-persisted trace and revision data into inspection surfaces, and adds the promotion event as a first-class, recorded lifecycle transition.

## Goals / Non-Goals

**Goals:**

- Inspect any historical query (`trace list`/`show`) and replay it against the current corpus with a clear diff (`trace replay`).
- Diff any two revisions of a wiki page — body and frontmatter (`page diff`), with a revision history listing.
- Record and list promotion events (`page promote`, `promotions list`) so a page's lifecycle is inspectable.

**Non-Goals:**

- TUI screens for any of these surfaces (Phase 8); Phase 7 is CLI + a read/replay library the TUI will call.
- The curator slow-loop that generates promotions from `graph_curation_signals` (Phase 9).
- Graph side effects of promotion (adding `GROUNDS`/`SYNTHESIZES` edges) — Phase 9.
- Delta/compressed revision storage — full-body snapshots stay (v0.2 may revisit).
- Trace TTL/pruning — deferred.

## Decisions

### Decision: replay is read-only by default, diffs the final ranking

`compendium trace replay <id>` loads the stored trace, re-runs its `query_text` through `pipeline.query(text, persist=False)` against the current corpus, and renders a diff of the stored `final_ranking` against the fresh one: pages added/removed, pages that moved rank, the coverage-score delta, and any change in `fallback_to_chunks`. Read-only is the default because ADR-007 frames replay as a regression check (Phase 10 CI replays a fixed trace set and asserts no quality regression), and flooding `query_traces` with replay rows would pollute that very signal. A `--persist` flag records a fresh trace for the replay when the operator wants it captured.

**Alternatives considered:** always persisting (truer to "every query is traced," but grows the table on every CI replay); diffing the whole `pipeline` JSON rather than `final_ranking` (noisier — per-stage candidate churn obscures the user-visible answer change). The final-ranking diff plus coverage/fallback deltas is the signal that matches "did the answer change?"

### Decision: revision diff is a unified body diff plus a frontmatter key-delta

`compendium page diff <slug> <rev_a> <rev_b>` resolves the page by slug, loads the two `wiki_page_revisions` rows, and renders: a unified text diff of the markdown bodies (stdlib `difflib.unified_diff`) and a key-by-key frontmatter delta (added/removed/changed keys from the stored `frontmatter` JSONB). Revisions are addressed by a short ordinal or by revision id; `compendium page revisions <slug>` lists them with ordinal, id, generator, created_at, and notes so the operator can pick two. No new dependency — `difflib` is stdlib.

### Decision: promotion is a recorded transition, not just a status flip

`compendium page promote <slug> --to {canonical,deprecated}` is the v0.1 promotion primitive: in one transaction it writes a `human`-generator `wiki_page_revisions` snapshot of the current body (so `from_revision_id`/`to_revision_id` are real), updates `wiki_pages.status`, and inserts a `promotion_events` row with the appropriate `promotion_kind` (`draft_to_canonical` or `canonical_to_deprecated`). `merge`/`split` kinds are defined in the enum but not exposed as commands in v0.1. This makes promotions inspectable now (`promotions list`) and gives Phase 9's curator a single function (`repository.record_promotion`) to call rather than re-implementing the transition. Graph edge updates on promotion are explicitly Phase 9.

**Alternative considered:** a bare `UPDATE wiki_pages SET status` with no event row — simpler, but leaves `promotion_events` empty and the lifecycle invisible, contradicting the phase's acceptance.

### Decision: `compendium/trace/` is a thin read/replay library; repository owns SQL

Following the project's layering, all SQL lives in new `compendium/db/repository.py` read functions (`get_query_trace`, `list_query_traces`, `get_page_revisions`, `get_revision`, `record_promotion`, `list_promotion_events`). `compendium/trace/` holds pure-ish presentation/logic: the ranking-diff computation, the body/frontmatter diff rendering, and the replay orchestration (which calls the Phase 5 pipeline). This keeps the diff/replay logic unit-testable without a database and mirrors how `compendium/retrieve/` sits over `compendium/db/`.

## Risks / Trade-offs

- **Replay against a changed corpus can error if an indexed page was deleted** → Replay is defensive: it runs the live pipeline (which already tolerates missing entities) and diffs whatever comes back; a query that now returns nothing is a valid, reportable diff, not a crash.
- **Promotion writes a revision even when the body is unchanged** → Accepted: a status-only promotion still produces a `from`/`to` revision pair so the event has real endpoints; the body snapshot is identical, which is harmless at single-user scale (ADR-007 already accepts full-body snapshots).
- **Slug collisions across page kinds** → `page diff`/`promote` resolve by slug; slugs are unique per kind in the schema, so the resolver disambiguates by kind when needed (error if ambiguous) rather than guessing.
- **Replay diff semantics could drift from the TUI's later view** → Mitigated by putting the diff computation in `compendium/trace/` as a reusable function the Phase 8 TUI imports, not re-implements.

## Migration Plan

No schema migration. No new dependency (`difflib` is stdlib; replay reuses Phase 5). Rollback is removing `compendium/trace/`, the new CLI subcommands, and the new repository read/promotion functions; `query_traces`/`wiki_page_revisions`/`promotion_events` and all data are untouched.

## Open Questions

- **Revision addressing in `page diff`.** The plan supports both a short ordinal (1-based, oldest-first) and a revision-id prefix. Confirm at the review gate that an ordinal is the primary ergonomics (ids are long UUIDs); the plan defaults to "ordinal, with id accepted."
- **`promotions list` scope.** Global (all pages, most recent first) versus per-page (`--slug`). The plan ships both: bare lists globally, `--slug` filters to one page.
