## ADDED Requirements

### Requirement: Semantic edges have a system-of-record home in PostgreSQL

Every semantic edge (`RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, `CONTRADICTS`) SHALL
be persisted in a PostgreSQL `semantic_edges` table, keyed on the directed pair
`(edge_type, from_label, from_id, to_label, to_id)`, carrying the ADR-010 provenance
(`extracted_by`, `model`, `confidence`, `extracted_at`, `source_revision_id`, `weight`).
The table SHALL hold one row per directed edge, mirroring Memgraph's `MERGE`.

#### Scenario: A written edge persists a row

- **WHEN** a semantic edge is written through the dual-write coordinator and the write is not a collision
- **THEN** a `semantic_edges` row exists for the directed pair with the edge's provenance, and re-writing the same edge updates that row in place rather than inserting a duplicate

### Requirement: One coordinator dual-writes the resolved edge

Every semantic-edge write SHALL go through one coordinator
(`compendium/graph/semantic_edges.py::record_semantic_edge`) that writes the resolved edge
to both Memgraph and PostgreSQL. The coordinator SHALL delegate curator-protection and
symmetric canonicalisation to `schema.upsert_semantic_edge` (the graph remains their
arbiter) and mirror only the resolved outcome to PostgreSQL: on a `collision` it SHALL
leave PostgreSQL untouched; otherwise it SHALL upsert the row. The graph schema module
SHALL NOT import the database layer.

#### Scenario: Curator link writes both stores

- **GIVEN** two existing pages
- **WHEN** `compendium graph link` creates a curator edge between them
- **THEN** the edge exists in Memgraph with `extracted_by="curator"` and a matching `semantic_edges` row exists in PostgreSQL

#### Scenario: An LLM write never clobbers a curator edge in either store

- **GIVEN** a curator edge exists for a pair
- **WHEN** the LLM extractor proposes the same pair
- **THEN** `schema.upsert_semantic_edge` reports `collision`, the Memgraph edge keeps its curator provenance, and the PostgreSQL row is left unchanged

### Requirement: `graph rebuild` replays semantic edges and no longer wipes them

`compendium graph rebuild` SHALL, after re-projecting the structural edges from PostgreSQL
plus the vault, replay every semantic edge from `semantic_edges` into the freshly dropped
graph through `schema.upsert_semantic_edge`. A rebuild SHALL NOT result in the loss of any
curator, `SYNTHESIZES`, or LLM-extracted edge that has a `semantic_edges` row.

#### Scenario: Curator and SYNTHESIZES edges survive a rebuild

- **GIVEN** a curator edge and a `SYNTHESIZES` edge each have a `semantic_edges` row
- **WHEN** `compendium graph rebuild` runs
- **THEN** both edges are present in the rebuilt graph with their original provenance, and the rebuild stays deterministic from the corpus revision plus the edge rows

#### Scenario: LLM-extracted edges survive a rebuild

- **GIVEN** an LLM-extracted `RELATED_TO` edge has a `semantic_edges` row
- **WHEN** `compendium graph rebuild` runs
- **THEN** the edge is present in the rebuilt graph with `extracted_by="llm"` and its confidence/model/weight provenance intact

### Requirement: A one-shot backfill captures pre-existing in-graph edges

The system SHALL provide `compendium graph backfill-edges`, which reads the semantic edges
currently in Memgraph (with provenance) and writes their `semantic_edges` rows, so edges
created before this capability are captured before the first rebuild under it. The command
SHALL be idempotent.

#### Scenario: Backfill then rebuild preserves legacy edges

- **GIVEN** semantic edges exist only in Memgraph (created before persistence) and have no `semantic_edges` rows
- **WHEN** `compendium graph backfill-edges` runs and then `compendium graph rebuild` runs
- **THEN** the edges have `semantic_edges` rows after the backfill and are present in the graph after the rebuild; re-running the backfill inserts no duplicates
