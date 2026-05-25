## ADDED Requirements

### Requirement: Graph node schema

The system SHALL represent the corpus as four Memgraph node labels — `:Source`, `:Concept`, `:Topic`, and `:Chunk` — with the properties specified in `docs/Compendium.md` § Memgraph schema. Each node's `id` SHALL be the corresponding PostgreSQL UUID. The system SHALL create indexes on `id` for all four labels and on `slug` for `:Concept` and `:Topic`.

#### Scenario: Node labels and indexes are created

- **WHEN** the graph schema is initialized
- **THEN** the `id` indexes for `:Source`, `:Concept`, `:Topic`, `:Chunk` and the `slug` indexes for `:Concept`, `:Topic` exist

#### Scenario: A node mirrors its PostgreSQL row

- **WHEN** a wiki page or chunk is projected into the graph
- **THEN** a node of the matching label exists whose `id` is the PostgreSQL UUID and whose properties mirror the documented columns

### Requirement: Idempotent node and edge upserts

The system SHALL upsert nodes by `MERGE` on `id`, so re-projecting an entity does not create a duplicate node. The system SHALL create edges by merging both endpoint nodes by `id` before merging the relationship, so an edge write does not depend on node-write order and does not fail when an endpoint has not been written yet.

#### Scenario: Re-upserting a node is idempotent

- **WHEN** the same entity is projected into the graph twice
- **THEN** exactly one node exists for it, with the latest properties

#### Scenario: An edge write creates missing endpoints

- **WHEN** an edge is written before one of its endpoint nodes has been projected
- **THEN** the endpoint node is merged by id and the edge is created without error

### Requirement: Automatic structural edges

The system SHALL build the three v0.1 automatic edge types from PostgreSQL plus the vault: `PART_OF` (`(:Chunk)->(:Source)`, `(:Concept)->(:Topic)`, `(:Topic)->(:Topic)`), `EVIDENCES` (`(:Source)->(:Chunk)`), and `GROUNDS` (`(:Concept)->(:Chunk)`). The curator-driven semantic edges (`RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, `CONTRADICTS`) SHALL be defined in the schema but SHALL NOT be populated in this phase.

#### Scenario: Chunks are linked to their source

- **WHEN** a source and its chunks are projected
- **THEN** each `:Chunk` has a `PART_OF` edge to its `:Source`, and the `:Source` has an `EVIDENCES` edge to each of its chunks

#### Scenario: Concept pages are grounded in chunks

- **WHEN** a concept page that cites chunks is projected
- **THEN** the `:Concept` has a `GROUNDS` edge to each cited `:Chunk`

#### Scenario: Semantic edges are not auto-populated

- **WHEN** the graph is built in this phase
- **THEN** no `RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, or `CONTRADICTS` edges are created

### Requirement: GROUNDS edges derived from the vault grounding section

The system SHALL derive `GROUNDS` edges by parsing the cited chunk UUIDs from each concept page's `## Grounding` section in the canonical vault file. A cited UUID that does not correspond to an existing `chunks` row SHALL be skipped rather than producing a dangling edge.

#### Scenario: Grounding citations become edges

- **WHEN** a concept page's `## Grounding` section cites chunk UUIDs that exist in `chunks`
- **THEN** a `GROUNDS` edge is created from the concept to each of those chunks

#### Scenario: A stale citation is skipped

- **WHEN** a cited UUID has no matching `chunks` row
- **THEN** no edge is created for it and the projection does not error

### Requirement: Sync-state integration for the memgraph kind

Every page write and chunk write SHALL enqueue an `index_sync_state` row for the `memgraph` `index_kind`. The sync worker SHALL drain `memgraph` rows by projecting the entity's node and its automatic edges and marking the row `indexed`; a failure SHALL record `last_error`, increment `attempts`, and mark the row `failed`, consistent with the OpenSearch and Qdrant kinds.

#### Scenario: A write enqueues the memgraph kind

- **WHEN** a page or chunk is written
- **THEN** `index_sync_state` contains a `pending` row for that entity for the `memgraph` kind

#### Scenario: Draining projects the entity into the graph

- **WHEN** `compendium index sync` drains a pending `memgraph` row
- **THEN** the entity's node and automatic edges exist in Memgraph and the row is marked `indexed`

### Requirement: Deterministic graph rebuild

The system SHALL provide `compendium graph rebuild` that drops the graph, recreates the indexes, and repopulates every node and every automatic edge from PostgreSQL plus the vault. Running it from an empty graph SHALL reproduce the same node and edge counts as an incremental sync of the same corpus.

#### Scenario: Rebuild from empty restores the graph

- **WHEN** the graph is dropped and `compendium graph rebuild` is run
- **THEN** the node counts per label and edge counts per type match the corpus

### Requirement: Graph status reporting

The system SHALL provide `compendium graph status` that reports the node count per label and the edge count per type, and indicates when Memgraph is unreachable.

#### Scenario: Status reports counts

- **WHEN** `compendium graph status` runs against a populated graph
- **THEN** it prints the per-label node counts and per-type edge counts

#### Scenario: Status handles an unreachable graph

- **WHEN** Memgraph is not reachable
- **THEN** `compendium graph status` reports it as unreachable rather than raising
