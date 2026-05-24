## ADDED Requirements

### Requirement: OpenSearch indexes

The system SHALL create two OpenSearch indexes, `pages` and `chunks`, with the analyzers and `dynamic: strict` mappings specified in `docs/Compendium.md` § OpenSearch indexes. Each document's `_id` SHALL be the entity UUID so that writes are idempotent upserts.

#### Scenario: Indexes are created with the documented mapping

- **WHEN** the OpenSearch indexes are created from their schema
- **THEN** the `pages` and `chunks` indexes exist with the `compendium_text` analyzer and strict mappings

#### Scenario: Re-indexing a page is idempotent

- **WHEN** the same page is indexed twice
- **THEN** the `pages` index contains exactly one document for it, keyed by its UUID

### Requirement: Qdrant collections

The system SHALL create two Qdrant collections, `pages` and `chunks`, with 1024-dimension Cosine vectors, the documented HNSW parameters, and the documented payload indexes. Each point id SHALL be the entity UUID.

#### Scenario: Collections are created with the documented definition

- **WHEN** the Qdrant collections are created from their schema
- **THEN** the `pages` and `chunks` collections exist with 1024-dim Cosine vectors and payload indexes on the documented fields

### Requirement: Query and document embedding

The system SHALL embed text through an injectable `Embedder` seam. The default adapter SHALL call the pinned `EMBED_MODEL` at the configured OpenAI-compatible endpoint; a deterministic stub adapter SHALL produce fixed-dimension vectors without a network call for tests and offline verification.

#### Scenario: Stub embedder is deterministic and offline

- **WHEN** the stub embedder embeds the same text twice
- **THEN** it returns identical 1024-dimension vectors without contacting an endpoint

### Requirement: Sync-state enqueue on write

Every page write SHALL enqueue `index_sync_state` rows for `opensearch_pages` and `qdrant_pages`; every chunk write SHALL enqueue rows for `opensearch_chunks` and `qdrant_chunks`. Enqueue SHALL be idempotent: re-enqueuing an entity resets its row to `pending`.

#### Scenario: A page write enqueues its index kinds

- **WHEN** a page is written to the vault
- **THEN** `index_sync_state` contains a `pending` row for that page id for `opensearch_pages` and one for `qdrant_pages`

#### Scenario: Re-enqueue resets state to pending

- **WHEN** an entity that is already `indexed` is written again
- **THEN** its `index_sync_state` rows return to `pending`

### Requirement: Sync worker drains the queue

The system SHALL provide a worker that processes `pending` `index_sync_state` rows: it loads the entity, projects the document, embeds for Qdrant targets, upserts to the target index by UUID, and marks the row `indexed`. On failure it SHALL record `last_error`, increment `attempts`, and mark the row `failed`. `compendium index sync` SHALL run the worker.

#### Scenario: Draining indexes pending entities

- **WHEN** `compendium index sync` runs with pending rows
- **THEN** the corresponding documents appear in OpenSearch and Qdrant and the rows become `indexed`

#### Scenario: A failed write is recorded, not lost

- **WHEN** indexing an entity raises an error
- **THEN** its `index_sync_state` row is marked `failed` with `last_error` set and `attempts` incremented, and a later drain retries it

### Requirement: Deterministic reindex

`compendium reindex {pages|chunks|all}` SHALL drop and recreate the target index and collection and repopulate them from PostgreSQL plus the vault, producing the same state as a clean replay.

#### Scenario: Rebuild from empty restores the corpus

- **WHEN** the indexes are dropped and `compendium reindex all` runs over the Phase 3 corpus
- **THEN** OpenSearch and Qdrant contain the expected counts of pages and chunks, and a known query returns the same top result as before the rebuild

### Requirement: Index status

`compendium index status` SHALL report, per index kind, the count of documents and the `index_sync_state` breakdown (pending, indexed, failed), so drift and backlog are visible.

#### Scenario: Status reports counts and sync lag

- **WHEN** `compendium index status` runs
- **THEN** it reports document counts per index and the pending/indexed/failed counts from `index_sync_state`
