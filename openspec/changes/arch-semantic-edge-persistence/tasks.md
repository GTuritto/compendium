# Tasks — arch-semantic-edge-persistence

Correctness fix: give semantic edges a PostgreSQL home so `graph rebuild` replays them
instead of wiping them. The graph stays the arbiter of curator-protection and
canonicalisation; PostgreSQL durably mirrors the resolved edge. One commit per sub-phase,
green at HEAD. Boxes unchecked until implementation is approved.

## 1. Migration + repository functions (sub-phase a)

- [ ] 1.1 `migrations/versions/0013_semantic_edges.py` (`down_revision="0012"`): table `semantic_edges` with `edge_type`, `from_label`, `from_id`, `to_label`, `to_id`, the provenance columns (`extracted_by`, `model`, `confidence`, `extracted_at`, `source_revision_id`, `weight`), `created_at`, and a UNIQUE index on `(edge_type, from_label, from_id, to_label, to_id)`. Additive; no change to existing tables.
- [ ] 1.2 `db/repository.py`: `upsert_semantic_edge_row(conn, edge_type, from_label, from_id, to_label, to_id, provenance)` (ON CONFLICT on the unique tuple → update provenance), `delete_semantic_edge_row(conn, …)`, `all_semantic_edges(conn) -> list[...]` returning the tuple + provenance. Raw SQL, no ORM (ADR-004).
- [ ] 1.3 `tests/test_semantic_edge_repo.py`: round-trip (upsert → all returns the row with provenance intact); ON CONFLICT updates in place (no duplicate); delete removes the row.

## 2. The dual-write coordinator + writers route through it (sub-phase b)

- [ ] 2.1 `compendium/graph/semantic_edges.py`: `record_semantic_edge(conn, driver, edge_type, from_label, from_id, to_label, to_id, *, provenance) -> str` — call `schema.upsert_semantic_edge`; on `collision` return without touching PostgreSQL; otherwise `repository.upsert_semantic_edge_row` and return the disposition. `schema.py` stays pure-graph (unchanged).
- [ ] 2.2 Route the three writers through the coordinator, passing the `conn` in scope: `graph/links.py` (keep its `connection()` open across the graph write), `curate/lifecycle.py:80` (the promote-transaction `conn`; the `SYNTHESIZES` row commits atomically with the status flip), `curate/extract.py:332/334` (the curate-run `conn`; keep the `upsert_extracted_edge` extractable-type assertion in front).
- [ ] 2.3 Mirror the LLM collision/refresh outcome to PostgreSQL via the coordinator's disposition handling; the curator unlink path (if/when present) deletes the row.
- [ ] 2.4 `tests/test_semantic_edge_coordinator.py`: a curator link writes both a graph edge and a PostgreSQL row; an LLM write that collides with a curator edge writes neither a new graph edge nor a row (`collision`); an LLM refresh updates both.

## 3. Replay pass + backfill (sub-phase c)

- [ ] 3.1 `graph/rebuild.py::rebuild()`: after the structural projection loops, iterate `repository.all_semantic_edges(conn)` and `schema.upsert_semantic_edge` each into the freshly dropped graph. Confirm `GraphReport` edge counts include the semantic types.
- [ ] 3.2 `compendium graph backfill-edges` (`__main__.py` + a `backfill_edges()` in `graph/semantic_edges.py`): read current in-graph semantic edges (with provenance) → `upsert_semantic_edge_row`. Idempotent (re-run is a no-op against the unique index). `cli/render.py` renders its count report.
- [ ] 3.3 `tests/test_graph_rebuild_replay.py`: write curator + `SYNTHESIZES` + LLM edges → `graph rebuild` → all three return with provenance; curator protection resolves identically before and after a rebuild; backfill of in-graph-only edges produces rows and a subsequent rebuild preserves them.

## 4. Close-out (sub-phase d)

- [ ] 4.1 New ADR (`docs/Compendium.md` + `docs/DECISIONS.md`): "semantic edges are system-of-record data in PostgreSQL, projected into Memgraph; `graph rebuild` replays them." Note it reconciles ADR-004 / ADR-005 (graph is now fully derived).
- [ ] 4.2 `CONTEXT.md`: update **edge provenance** / **LLM-extracted edge** to note provenance is now persisted in `semantic_edges`, not graph-only.
- [ ] 4.3 Append an "Arch — semantic-edge persistence" smoke section to `tests/manual/smoke_test.md`: `graph link` + `graph rebuild` preserves the curator edge; promote + rebuild preserves `SYNTHESIZES`; `backfill-edges` captures legacy edges.
- [ ] 4.4 **Acceptance:** semantic edges have a PostgreSQL home; all three writers dual-write through the coordinator; `schema.py` imports no db layer; `graph rebuild` preserves curator / `SYNTHESIZES` / LLM edges with provenance (the rebuild-preserves test is the gate); backfill captures pre-existing in-graph edges; fast tier and golden green.
- [ ] 4.5 `openspec validate arch-semantic-edge-persistence` clean.
