## Context

Fifth post-v0.2 architecture-fix change, and the first that is a **correctness fix
rather than a deepening** (architecture review #3, candidate 1; the standing top item of
the arch-fix track). `compendium graph rebuild` permanently wipes every semantic edge
because the edges live only in Memgraph, a derived store the rebuild is licensed to drop
and re-derive. Structural edges survive because they are re-derived from PostgreSQL + the
vault; semantic edges have no such home.

Target: not a missing seam — the write seam (`schema.upsert_semantic_edge`) already
exists and is already deep (one path for three writers, owning canonicalisation, curator
protection, provenance). The seam writes to the wrong store. The fix gives the edges a
system-of-record home so the seam's durability matches its depth, and the rebuild can
replay them like everything else.

## Goals / Non-Goals

**Goals:**

- A `semantic_edges` table in PostgreSQL: the system-of-record home, with the ADR-010
  provenance bag, one row per directed edge.
- A dual-write coordinator that writes the resolved edge to both stores; the three
  writers route through it; `schema.py` stays pure-graph.
- A replay pass in `rebuild()` that re-projects semantic edges from PostgreSQL after the
  structural projection.
- A one-shot backfill so pre-existing in-graph edges are captured before the first new rebuild.
- Reconcile ADR-004 / ADR-005 (graph fully derived) without changing the
  curator-protection / canonicalisation rules.

**Non-Goals:**

- Persisting structural edges (already derivable).
- Memgraph on the incremental sync queue (separate carry-forward).
- Any change to which writes win (curator vs LLM); the graph stays the arbiter.

## Decisions

### Decision: a `semantic_edges` table keyed on the directed pair

`migrations/versions/0013_semantic_edges.py`, `down_revision="0012"`:

```text
semantic_edges
  id               uuid pk default gen_random_uuid()
  edge_type        text not null          -- RELATED_TO / PREREQUISITE_FOR / SYNTHESIZES / CONTRADICTS
  from_label       text not null          -- Source / Concept / Topic
  from_id          text not null          -- the Memgraph node id (source_id or page id)
  to_label         text not null
  to_id            text not null
  extracted_by     text not null          -- 'curator' | 'llm'
  model            text                   -- when extracted_by = 'llm'
  confidence       double precision        -- 0.0–1.0 when extracted_by = 'llm'
  extracted_at     text                   -- ISO-8601 (matches the graph property)
  source_revision_id uuid                 -- the revision that triggered an extraction
  weight           double precision
  created_at       timestamptz not null default now()
  UNIQUE (edge_type, from_label, from_id, to_label, to_id)
```

One row per directed edge, mirroring Memgraph's `MERGE` on the same tuple. The provenance
is stored as **typed columns** (queryable, prunable by predicate — the same reason
ADR-010 put provenance on the graph edge), not a JSONB blob.

**Alternative considered:** an `edge_type` enum like the other native PostgreSQL enums.
Rejected for this change — `text` with a check against the `EdgeType` registry keeps the
migration additive and avoids an enum-value migration; an enum can be a later tightening.

### Decision: a dual-write coordinator; `schema.py` stays pure-graph

`compendium/graph/semantic_edges.py`:

```text
def record_semantic_edge(conn, driver, edge_type, from_label, from_id,
                         to_label, to_id, *, provenance) -> str:
    disposition = schema.upsert_semantic_edge(
        driver, edge_type, from_label, from_id, to_label, to_id,
        provenance=provenance,
    )                                   # 'written' | 'refreshed' | 'collision'
    if disposition == "collision":
        return disposition              # protected curator row already in PG; leave it
    repository.upsert_semantic_edge_row(conn, edge_type, from_label, from_id,
                                        to_label, to_id, provenance)
    return disposition
```

The coordinator owns the cross-store write. `schema.upsert_semantic_edge` keeps taking
only `driver` and remains the arbiter of curator-protection + symmetric canonicalisation
against the live graph; the coordinator simply mirrors its **resolved** outcome to
PostgreSQL. This keeps the graph layer from importing the db layer anywhere except this
one new module (which is the cross-store seam by design — the same shape `rebuild.py`
already has).

**Alternative considered:** thread a `conn` into `schema.upsert_semantic_edge` so it
dual-writes directly. Rejected — it couples the pure-graph schema module to `psycopg` at
the lowest level and spreads the db dependency, where the coordinator concentrates it in
one named seam.

**Connection ownership:** the coordinator takes the `conn` already in scope at each
caller — `curate/lifecycle.py::address_on_promote` (inside the promote transaction, so the
`SYNTHESIZES` row commits atomically with the signal-status flip), `curate/extract.py`
(the curate-run connection), and `graph/links.py` (which keeps its `connection()` open
across the graph write rather than closing it first).

### Decision: replay pass in `rebuild()`, after the structural projection

```text
def rebuild():
    with graph_connection() as driver:
        schema.drop_all(driver); schema.ensure_indexes(driver)
        with connection() as conn:
            ... project_source / project_chunk / project_page ...   # structural, unchanged
            for e in repository.all_semantic_edges(conn):           # NEW replay pass
                schema.upsert_semantic_edge(
                    driver, e.edge_type, e.from_label, e.from_id,
                    e.to_label, e.to_id, provenance=e.provenance,
                )
        return _report(driver)
```

Order-free: the replay runs against a freshly dropped graph, so no edge pre-exists and the
provenance stored in PostgreSQL is re-stamped verbatim. Determinism now rests on the
PostgreSQL rows (structural + semantic) plus the corpus revision — strictly stronger than
today, where the semantic edges were not deterministic at all (they were whatever happened
to survive in Memgraph).

### Decision: store-as-written; faithful replay

The PostgreSQL row stores exactly the directed tuple and provenance that
`schema.upsert_semantic_edge` resolved and wrote to the graph. For symmetric `RELATED_TO`,
the LLM path already canonicalises orientation before the write, and a curator edge keeps
its caller orientation (so fast-loop expansion can still walk it) — both are mirrored
as-is. Replay reproduces the same orientation, so the post-rebuild graph is identical to
the pre-rebuild graph. The unique index enforces one row per directed tuple, matching the
graph's `MERGE`.

### Decision: a one-shot `graph backfill-edges` verb

Before the first rebuild under the new code, the existing in-graph semantic edges have no
PostgreSQL rows. `compendium graph backfill-edges` reads them out of Memgraph (with
provenance) and writes the rows, so the transition captures rather than loses existing
curator work. Explicit CLI verb (not an automatic migration step) so it is observable and
idempotent — re-running it is a no-op against the unique index.

## Risks / Trade-offs

- **Dual-write divergence.** A graph write that succeeds while the PostgreSQL write fails
  (or vice versa) could drift. Mitigation: the PostgreSQL write follows the resolved graph
  disposition in the same coordinator call; for the lifecycle path it shares the promote
  transaction. A failed PostgreSQL upsert raises, surfacing the divergence rather than
  hiding it. Full two-phase consistency is out of scope for a single-user local system.
- **Backfill on a corrupted graph.** If the pre-fix graph already lost edges, backfill can
  only capture what remains. Mitigation: documented as a one-shot capture of *current*
  state, not a recovery of already-lost edges.
- **Migration on an existing deployment.** Additive table; no change to existing rows.
  The new write path is inert until edges are written or backfilled.

## Migration Plan

1. Land `0013_semantic_edges` + the three repository functions (no behaviour change yet).
2. Add the coordinator and route the three writers through it (edges now dual-write).
3. Add the replay pass + the backfill verb.
4. On a live vault: run `compendium graph backfill-edges` once, then `graph rebuild`
   preserves. Rollback = revert the branch; the table is harmless if unused.

Each step green with the existing graph + curation suites. The gate is the
rebuild-preserves integration test (write edges → rebuild → edges return with provenance).

## Open Questions

- Coordinator owns the cross-store write in `graph/semantic_edges.py` (plan — keeps
  `schema.py` pure-graph) vs. threading a `conn` into `schema.upsert_semantic_edge`?
  Plan: the coordinator.
- `edge_type` as `text` + registry check (plan — additive migration) vs. a native enum?
  Plan: `text` now; enum is a later tightening if earned.
- Backfill as an explicit CLI verb (plan) vs. an automatic first-run step? Plan: explicit
  verb (observable, idempotent).
