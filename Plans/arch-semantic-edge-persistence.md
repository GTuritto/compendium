# Arch fix — Semantic-edge persistence + replay: Implementation Plan

Date: 2026-06-07
Branch: `arch/semantic-edge-persistence` (off `main`)
OpenSpec change: `openspec/changes/arch-semantic-edge-persistence/`
Spec source: architecture review #3 (deep edition), candidate 1 — the standing top item
of the arch-fix track. Umbrella roadmap: [Plans/arch-review-3-plan.md](arch-review-3-plan.md) § Phase 1.

## Goal

Give the three semantic-edge writers (curator `graph link`, the `SYNTHESIZES` promote
lifecycle, the LLM extractor) a PostgreSQL home so `compendium graph rebuild` replays them,
ending the silent data-loss where a rebuild's `drop_all` permanently wipes every
curator / `SYNTHESIZES` / extracted edge.

## Why this plan exists

It locks in that the fix is **persist-upstream-then-replay**, not
teach-rebuild-to-spare-in-graph-state. Sparing in-graph edges would make Memgraph a second
source of truth (violates ADR-004) and make the rebuild depend on graph history (breaks the
determinism `rebuild.py`'s docstring promises). Persisting the edges in PostgreSQL keeps
Memgraph fully derived (honours ADR-005) and keeps the drop-and-reproject discipline
unchanged. It also pins the one structural decision — a dual-write **coordinator**
(`graph/semantic_edges.py`) so `schema.py` stays pure-graph — and the one invariant: the
graph stays the arbiter of curator-protection / canonicalisation; PostgreSQL mirrors the
resolved edge.

## Branch + commit strategy

- Create `arch/semantic-edge-persistence` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch-SE-a — migration + repo`, `Arch-SE-b — coordinator`, …), green at HEAD.
- Final commit: `Arch fix complete — semantic-edge persistence + replay`.
- Commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — Migration + repository functions

**Purpose:** Land the system-of-record home with zero behaviour change.

**Tasks:**

1. `migrations/versions/0013_semantic_edges.py` (`down_revision="0012"`): `semantic_edges`
   table — `edge_type`, `from_label`, `from_id`, `to_label`, `to_id`, provenance columns
   (`extracted_by`, `model`, `confidence`, `extracted_at`, `source_revision_id`, `weight`),
   `created_at`, UNIQUE on the directed tuple. Additive.
2. `db/repository.py`: `upsert_semantic_edge_row` (ON CONFLICT → update provenance),
   `delete_semantic_edge_row`, `all_semantic_edges`. Raw SQL, no ORM.

**Files added:** `migrations/versions/0013_semantic_edges.py`, `tests/test_semantic_edge_repo.py`
**Files modified:** `compendium/db/repository.py`
**Decision flagged:** provenance as typed columns (queryable/prunable), not JSONB; `edge_type` as `text` + registry check (additive), not a native enum.

### b — Dual-write coordinator; writers route through it

**Purpose:** One home writes the resolved edge to both stores; `schema.py` stays pure-graph.

**Tasks:**

1. `compendium/graph/semantic_edges.py`: `record_semantic_edge(conn, driver, …)` — delegate
   to `schema.upsert_semantic_edge` for the resolved disposition; mirror non-`collision`
   outcomes to PostgreSQL via `upsert_semantic_edge_row`.
2. Route `graph/links.py`, `curate/lifecycle.py:80`, `curate/extract.py:332/334` through the
   coordinator with the `conn` in scope (links keeps its `connection()` open across the graph
   write; lifecycle reuses the promote-transaction conn so the `SYNTHESIZES` row commits atomically).
3. Keep `upsert_extracted_edge`'s extractable-type assertion in front of the extractor path.

**Files added:** `compendium/graph/semantic_edges.py`, `tests/test_semantic_edge_coordinator.py`
**Files modified:** `compendium/graph/links.py`, `compendium/curate/lifecycle.py`, `compendium/curate/extract.py`
**Decision flagged:** coordinator owns the cross-store write (the only place the graph layer touches the db layer); `schema.upsert_semantic_edge` keeps taking only `driver`.

### c — Replay pass + backfill

**Purpose:** Rebuild restores semantic edges; capture existing in-graph edges once.

**Tasks:**

1. `graph/rebuild.py::rebuild()`: after the structural projection loops, replay
   `repository.all_semantic_edges(conn)` via `schema.upsert_semantic_edge` into the dropped graph.
2. `compendium graph backfill-edges` (`__main__.py` + `backfill_edges()` in
   `graph/semantic_edges.py`): read current in-graph semantic edges → PostgreSQL rows; idempotent.
   `cli/render.py` renders the count report.

**Files modified:** `compendium/graph/rebuild.py`, `compendium/__main__.py`, `compendium/cli/render.py`
**Files added:** `tests/test_graph_rebuild_replay.py`
**Decision flagged:** store-as-written → faithful replay; determinism now rests on the PostgreSQL rows + corpus revision; backfill is an explicit one-shot verb (observable, idempotent).

### d — Close-out

**Purpose:** ADR, docs, smoke, validation.

**Tasks:** new ADR (graph fully derived); `docs/Compendium.md` + `docs/DECISIONS.md`;
`CONTEXT.md` (provenance now persisted); smoke section; `openspec validate`.

**Files modified:** `docs/Compendium.md`, `docs/DECISIONS.md`, `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
migrations/versions/
  0013_semantic_edges.py        # NEW
compendium/graph/
  semantic_edges.py             # NEW — record_semantic_edge + backfill_edges
  rebuild.py                    # MODIFIED — replay pass
  links.py                      # MODIFIED — route through coordinator
compendium/curate/
  lifecycle.py                  # MODIFIED — route through coordinator (promote txn)
  extract.py                    # MODIFIED — route through coordinator
compendium/db/
  repository.py                 # MODIFIED — 3 semantic-edge functions
compendium/
  __main__.py                   # MODIFIED — graph backfill-edges verb
  cli/render.py                 # MODIFIED — backfill report
tests/
  test_semantic_edge_repo.py        # NEW
  test_semantic_edge_coordinator.py # NEW
  test_graph_rebuild_replay.py      # NEW
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | repo round-trip | upsert → `all_semantic_edges` returns the row with provenance; ON CONFLICT updates in place; delete removes it |
| 2 | integration | dual-write | `graph link` writes a graph edge and a PostgreSQL row |
| 3 | integration | **rebuild preserves** (the gate) | write curator + `SYNTHESIZES` + LLM edges → `graph rebuild` → all three return with provenance |
| 4 | integration | protection survives replay | an llm/curator collision resolves identically before and after a rebuild |
| 5 | integration | backfill | in-graph-only edges → `graph backfill-edges` → rows appear; rebuild preserves; re-run inserts no duplicates |
| 6 | regression | fast tier + golden | `uv run pytest` and `-m golden` green |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-se.1 | Rebuild no longer wipes | `graph link` two pages; `graph rebuild`; `graph status` | curator edge count unchanged across the rebuild |
| arch-se.2 | SYNTHESIZES survives | promote a concept from a signal; `graph rebuild` | the `SYNTHESIZES` edge present after rebuild |
| arch-se.3 | Backfill captures legacy edges | on a pre-fix vault: `graph backfill-edges`; `graph rebuild` | counts match pre-backfill graph counts; re-run backfill is a no-op |

## Out of scope for this fix (do NOT build)

- Persisting structural edges (already derivable from PostgreSQL + the vault).
- Putting Memgraph on the incremental `index_sync_state` queue (separate carry-forward).
- Changing the curator-protection or canonicalisation rules (the graph stays the arbiter).
- `CONTRADICTS` autonomy (stays curator-only, ADR-010 deferral).

## Open questions to confirm before starting

1. Coordinator in `graph/semantic_edges.py` (recommended — keeps `schema.py` pure-graph) vs.
   threading a `conn` into `schema.upsert_semantic_edge`? Recommendation: the coordinator.
2. `edge_type` as `text` + registry check (recommended, additive migration) vs. a native
   PostgreSQL enum? Recommendation: `text` now; enum later if earned.
3. Backfill as an explicit CLI verb (recommended) vs. an automatic first-run step?
   Recommendation: explicit verb.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] `openspec validate arch-semantic-edge-persistence` clean.
- [ ] Testing plan passes; the rebuild-preserves test (row 3) is the gate.
- [ ] Smoke section appended to `tests/manual/smoke_test.md`.
- [ ] New ADR recorded; `docs/DECISIONS.md` + `CONTEXT.md` updated.
- [ ] PR marked ready for review.
