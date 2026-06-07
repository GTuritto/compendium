## Why

`compendium graph rebuild` silently and permanently destroys every curator-authored
semantic edge, every `SYNTHESIZES` edge, and every LLM-extracted edge. This is a
correctness defect, not a deepening — the standing top item from the post-v0.2
architecture-fix track (review #3, candidate 1).

Verified mechanism:

- `graph/rebuild.py::rebuild()` runs `schema.drop_all(driver)` (`MATCH (n) DETACH DELETE n`, `schema.py:244–247`), then re-projects **only the automatic structural edges** (`PART_OF`/`EVIDENCES`/`GROUNDS`) from PostgreSQL + the vault via `projection.project_*` (`rebuild.py:36–48`).
- The semantic edges have **no PostgreSQL home**. All three writers — the curator `graph link` (`graph/links.py:45`), the `SYNTHESIZES` promote lifecycle (`curate/lifecycle.py:80`), and the LLM extractor (`curate/extract.py:332/334`) — funnel through `schema.upsert_semantic_edge`, which writes the relationship and its provenance into Memgraph **and nowhere else** (`schema.py:179–183`).
- So `drop_all` deletes the only copy, and the re-projection cannot restore it: re-derivation reads PostgreSQL + the vault, and the edges are in neither. One rebuild — run to recover from corruption, pick up a projection change, or after a Memgraph version bump — wipes all hand-earned and autonomously-extracted semantic edges.

This contradicts ADR-005 ("the derived indexes rebuild from PostgreSQL plus the vault").
The defect is one layer up from the rebuild: semantic edges are durable, curator-authored
knowledge stored **only** in a store the system is licensed to drop. The rebuild's
drop-and-reproject discipline is correct for a derived store; the data simply was never
made derivable.

The fix is **persist-upstream-then-replay**, not teach-rebuild-to-spare-in-graph-state.
Sparing in-graph edges would make Memgraph a second source of truth (violates ADR-004)
and make the rebuild depend on graph history (breaks the determinism `rebuild.py`'s
docstring promises). Giving the edges a PostgreSQL home keeps Memgraph fully derived and
the rebuild deterministic — the edges become one more thing re-derived from the system of
record.

## What Changes

- **A `semantic_edges` table** (new migration `0013`, `down_revision="0012"`): the
  system-of-record home for every semantic edge, keyed on the directed pair
  `(edge_type, from_label, from_id, to_label, to_id)` with the ADR-010 provenance bag as
  typed columns (`extracted_by`, `model`, `confidence`, `extracted_at`,
  `source_revision_id`, `weight`). One row per edge, mirroring Memgraph's `MERGE`.
- **A dual-write coordinator** (`compendium/graph/semantic_edges.py`,
  `record_semantic_edge(conn, driver, …)`): the single home that writes the *resolved*
  edge to both stores. It calls `schema.upsert_semantic_edge` (which still arbitrates
  curator-protection + symmetric canonicalisation against the live graph and returns
  `written`/`refreshed`/`collision`); on a non-`collision` result it upserts the
  PostgreSQL row, on `collision` it leaves PostgreSQL untouched (the protected curator
  row already exists). The graph stays the arbiter; PostgreSQL durably mirrors the outcome.
- **The three writers route through the coordinator.** `graph/links.py`,
  `curate/lifecycle.py`, and `curate/extract.py` swap their direct
  `schema.upsert_semantic_edge` / `upsert_extracted_edge` calls for the coordinator,
  passing the `conn` already in scope (the `SYNTHESIZES` row then participates in the
  promote transaction). `schema.py` stays pure-graph — it never imports the db layer.
- **A replay pass in `rebuild()`.** After the structural projection loops, read
  `repository.all_semantic_edges(conn)` and `schema.upsert_semantic_edge` each into the
  freshly dropped graph. `GraphReport` edge counts already enumerate the semantic types.
- **A one-shot backfill** (`compendium graph backfill-edges`): read the current in-graph
  semantic edges into `semantic_edges`, so existing curator work is captured before the
  first rebuild under the new code rather than lost on the transition.

## Capabilities

### New Capabilities

- `semantic-edge-persistence`: semantic edges are system-of-record data in PostgreSQL
  (`semantic_edges`), written through one dual-write coordinator and re-projected into
  Memgraph; `graph rebuild` replays them, so a rebuild no longer destroys curator,
  `SYNTHESIZES`, or LLM-extracted edges. A one-shot backfill captures pre-existing
  in-graph edges.

### Modified Capabilities

<!-- This reconciles the graph with ADR-004 (PostgreSQL is the single source of truth)
and ADR-005 (the derived indexes rebuild from PostgreSQL + the vault) rather than
changing either. The curator-protection and canonicalisation rules of
schema.upsert_semantic_edge are unchanged; the graph remains their arbiter. The rebuild
keeps its drop-and-reproject discipline; it gains a second derive-from-Postgres pass. -->

## Impact

- **New code/files:** `migrations/versions/0013_semantic_edges.py`;
  `compendium/graph/semantic_edges.py` (the dual-write coordinator + backfill helper);
  `tests/test_semantic_edge_repo.py`, `tests/test_semantic_edge_coordinator.py`,
  `tests/test_graph_rebuild_replay.py`.
- **Modified files:** `compendium/db/repository.py` (three thin SQL functions:
  `upsert_semantic_edge_row`, `delete_semantic_edge_row`, `all_semantic_edges`);
  `compendium/graph/links.py`, `compendium/curate/lifecycle.py`,
  `compendium/curate/extract.py` (route through the coordinator);
  `compendium/graph/rebuild.py` (replay pass); `compendium/__main__.py` +
  `compendium/cli/render.py` (the `graph backfill-edges` verb + its report).
- **Schema migration:** yes — `0013_semantic_edges` (additive; no change to existing tables).
- **No new dependency.** Pure `psycopg` + `neo4j` over the existing access.
- **CLI:** one new verb (`graph backfill-edges`); `graph rebuild`/`status` output gains
  the replayed semantic-edge counts (already part of `GraphReport`).
- **Out of scope:**
  - **Persisting structural edges** — they are already derivable from PostgreSQL + the vault.
  - **Putting Memgraph on the incremental `index_sync_state` queue** — a separate carry-forward; this change only addresses the full-rebuild data-loss.
  - **Changing the curator-protection or canonicalisation rules** — the graph stays their arbiter; PostgreSQL mirrors the resolved outcome.
  - **`CONTRADICTS` autonomy** — unaffected; it stays curator-only (ADR-010 deferral).
