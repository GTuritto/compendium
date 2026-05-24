## Why

Phase 3 produces canonical wiki pages and stores sources and chunks in PostgreSQL, but nothing is searchable. Phase 5 retrieval is page-first hybrid search: BM25 over OpenSearch fused with dense vectors over Qdrant. Those two indexes do not exist yet. Phase 4 builds them as derived, rebuildable caches (ADR-005): populated from PostgreSQL and the vault, kept in sync through `index_sync_state`, and reconstructable from empty with a single command. Without Phase 4 there is nothing for Phase 5 to query.

## What Changes

- Two OpenSearch indexes, `pages` and `chunks`, created with the documented analyzers and `dynamic: strict` mappings from `docs/Compendium.md` § OpenSearch indexes. Document `_id` is the entity UUID, so upserts are idempotent.
- Two Qdrant collections, `pages` and `chunks`, created with 1024-dim Cosine vectors, the documented HNSW parameters, and the documented payload indexes.
- An embedding seam: a `Embedder` protocol with a real OpenAI-compatible adapter (`EMBED_MODEL` at `EMBEDDINGS_ENDPOINT`) and an injectable deterministic stub for tests, mirroring Phase 3's `Synthesizer`.
- Document projection: build the OpenSearch document and Qdrant payload for a page (structured fields from the `wiki_pages` row, body from the canonical vault file) and for a chunk (entirely from PostgreSQL).
- Sync enqueue: every page write and chunk write enqueues `index_sync_state` rows (`pending`) for its two index kinds.
- A sync worker that drains the pending queue: loads the entity, projects the document, embeds for Qdrant, upserts to the target index, and flips the row to `indexed`; failures record `last_error`, increment `attempts`, and mark `failed`.
- `compendium reindex {pages|chunks|all}`: drop and recreate the target index/collection and repopulate deterministically from PostgreSQL plus the vault. `compendium index {sync|status}`: drain the queue and report counts and sync lag.

## Capabilities

### New Capabilities

- `derived-indexes`: Populating and maintaining OpenSearch and Qdrant as derived indexes — index/collection schemas, the embedding seam, document projection, sync-state enqueue and the drain worker, and the deterministic rebuild command.

### Modified Capabilities

<!-- wiki-generation and ingestion gain a sync-enqueue side effect on write,
but their existing requirements are unchanged; no delta spec. -->

## Impact

- New code: `compendium/index/` (OpenSearch client and schemas, Qdrant client and schemas, embedder, document projection, sync worker), `compendium reindex` and `compendium index` CLI subcommands, and sync-enqueue hooks in `compendium/wiki/vault.py` and `compendium/ingest/pipeline.py`.
- New repository functions for `index_sync_state` (enqueue, claim pending, mark indexed/failed, counts).
- New dependencies: `opensearch-py` and `qdrant-client` (the two stores are already in the ADR-002 stack). Embeddings reuse the existing `openai` SDK.
- `docker-compose.yml` gains dev-only `opensearch` and `qdrant` services. The embedding model is served externally by Docker Model Runner, so it is not a compose service; index integration tests default to the stub embedder.
- No schema migration: `index_sync_state` and the `index_kind` / `sync_state` enums exist from Phase 1.
