# Spec — v0.5: agent object store + promote path (ADR-017)

## ADDED Requirements

### Requirement: Verbatim agent object storage
The system SHALL store agent objects in PostgreSQL (collection, key,
content_type, verbatim body, metadata, timestamps), upserting by
`(collection, key)` with last-write-wins, and return bodies byte-for-byte. The
store SHALL NOT be indexed into OpenSearch, Qdrant, or Memgraph.

#### Scenario: put then get round-trips verbatim
- **WHEN** an object is put and then got by key
- **THEN** the body is returned byte-for-byte with its content_type and metadata

#### Scenario: unpromoted objects are invisible to retrieval
- **WHEN** an object exists but has not been promoted
- **THEN** `query` and `ask` never return it (retrieval stays page-only)

### Requirement: Object verbs on the access surface and CLI
The facade SHALL expose `object_put`, `object_get`, `object_list`,
`object_delete`, and `object_promote` on both REST and MCP, with wire JSON
byte-identical to the CLI `--format json`. Mirrored CLI verbs SHALL exist.

#### Scenario: surface parity
- **WHEN** the same object operation runs via REST, MCP, and the CLI
- **THEN** the returned JSON is identical across all three

#### Scenario: list and delete
- **WHEN** `object_list` then `object_delete` then `object_get` run for a key
- **THEN** list shows it, delete removes it, and the subsequent get reports
  not-found

### Requirement: One-way promote into synthesis
`object_promote(key, kind)` SHALL run the object's body through the existing
ingest pipeline to become a `source` page (indexed, queryable), provenance-
linked to the object id. It SHALL NOT create concept pages or semantic edges.

#### Scenario: promote makes a queryable source
- **WHEN** a text object is promoted with `kind=note`
- **THEN** it becomes a source page that `query` returns, linked back to the
  object id

#### Scenario: promote does not synthesize
- **WHEN** an object is promoted
- **THEN** no concept page and no semantic edge are created
