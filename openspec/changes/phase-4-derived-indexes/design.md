## Context

This change implements Phase 4 (derived indexes) of `docs/COMPENDIUM_BUILD.md`. It builds on the Phase 1 schema (`index_sync_state`, the `index_kind` and `sync_state` enums) and the Phase 3 wiki (`wiki_pages`, `wiki_page_revisions`, the vault) plus the Phase 2 corpus (`sources`, `chunks`). The index mappings, collection definitions, sync model, and rebuild semantics are specified in `docs/Compendium.md` (ADR-005, § OpenSearch indexes, § Qdrant collections) and are implemented faithfully.

ADR-005 is the governing decision: OpenSearch and Qdrant are caches derived from PostgreSQL plus the vault, never the source of truth, and always rebuildable. A corrupted index is an operational problem, not a data-loss event.

## Goals / Non-Goals

**Goals:**

- The two OpenSearch indexes and two Qdrant collections exist with the documented schemas.
- A pinned embedding model behind an injectable seam produces query and document vectors.
- Page and chunk writes enqueue `index_sync_state`; a worker drains the queue into both indexes.
- `compendium reindex {pages|chunks|all}` rebuilds deterministically from empty.

**Non-Goals:**

- Retrieval, fusion, coverage, or fallback (Phase 5). Phase 4 populates indexes; it does not query them except to verify a rebuild.
- Memgraph and the `memgraph` index kind (Phase 6). Phase 4 enqueues only the four OpenSearch/Qdrant kinds.
- An always-on background sync daemon or scheduler (Phase 8 TUI / later). Draining is explicit in v0.1.
- pgvector and trace embeddings (Phase 5/7). Embeddings live only in Qdrant.

## Decisions

### Decision: page body from the canonical vault file, structured fields from PostgreSQL

For a page document, the structured fields (id, kind, title, slug, status, corpus_revision, topic_ids, parent_topic_id, source_id, source_kind, inspection_status, timestamps) come from the `wiki_pages` row, and the indexed `body` text comes from the canonical Markdown file at `wiki_pages.file_path` (parsed to strip frontmatter). This realizes "rebuildable from PostgreSQL plus the vault" literally and honors ADR-001 (the vault is canonical for content). A chunk document comes entirely from PostgreSQL: the `chunks` row plus the denormalized `sources.title`.

### Decision: the embedder is an injectable seam

Embedding is a `Embedder` protocol with one method, embed a batch of texts to vectors, mirroring Phase 3's `Synthesizer`. The real adapter calls the OpenAI-compatible embeddings endpoint (`EMBED_MODEL` at `EMBEDDINGS_ENDPOINT`) via the existing `openai` SDK. A deterministic stub adapter produces fixed 1024-dim vectors from a hash of the text, selected by `COMPENDIUM_EMBED_STUB` (mirroring `COMPENDIUM_SYNTH_STUB`) or by injection. Index integration tests use the stub so they do not depend on Docker Model Runner being up. The seam is also where Phase 10's cached/replay embedder will slot in for hermetic eval.

### Decision: writes enqueue, an explicit command drains

Every page write (`vault.write_page`) enqueues `index_sync_state` rows for `opensearch_pages` and `qdrant_pages`; every chunk write enqueues for `opensearch_chunks` and `qdrant_chunks`. Enqueue is idempotent via the table's unique constraint (re-enqueue resets an existing row to `pending`). Draining is not automatic: `compendium index sync` processes the pending queue, and `compendium reindex` repopulates inline. v0.1 has no always-on worker; eventual consistency is the operating model (ADR-005) and the drain is operator-triggered. This keeps ingestion fast and Phase 4 free of daemon concerns.

### Decision: the sync worker is defensive and records failures

The worker claims pending rows (ordered, using the partial `index_sync_pending_idx`), and for each: loads the entity, projects the document, embeds if the target is Qdrant, upserts by UUID `_id`/point id, and flips the row to `indexed`. On exception it increments `attempts`, stores `repr(exc)` in `last_error`, and marks the row `failed`; a later drain retries `failed` rows. Persistent failures surface via `compendium index status` (and the TUI in Phase 8).

### Decision: deterministic rebuild, verified per store

`compendium reindex pages|chunks|all` drops and recreates the target index/collection from its schema, then repopulates from PostgreSQL plus the vault. OpenSearch rebuilds are byte-stable, so verification asserts document counts and a sample of `_source` bodies. Qdrant's HNSW graph is not byte-stable, so verification re-runs a fixed query and asserts the top-K point IDs are stable within a small Jaccard distance, per `docs/Compendium.md` § Qdrant rebuild semantics. Determinism rests on the pinned `EMBED_MODEL` and stable body normalization (the Phase 3 content-hash normalization).

### Decision: index_kind matrix, memgraph deferred

The `index_kind` enum already encodes the entity-by-store matrix. Phase 4 uses `opensearch_pages`, `opensearch_chunks`, `qdrant_pages`, `qdrant_chunks`. The `memgraph` kind is enqueued only from Phase 6; Phase 4 never writes it.

## Risks / Trade-offs

- **Docker Model Runner not available during automated verification** → index integration tests default to the deterministic stub embedder; a separate opt-in test exercises the real endpoint. The stub is fixed 1024-dim, so Qdrant operations are exercised without a network embedder.
- **Eventual consistency means a query right after a write can miss new content** → Accepted per ADR-005; Phase 5 retrieval is defensive about staleness, and the operator drains with `compendium index sync` before relying on freshness.
- **Coupling write paths to sync enqueue** → Accepted; it is what "every write enqueues a sync row" (ADR-005) requires. Enqueue is a single repository call inside the existing write transaction.
- **Two new client dependencies** → Justified: OpenSearch and Qdrant are committed in ADR-002; their official clients are the supported way to talk to them.

## Migration Plan

No schema migration. New dependencies `opensearch-py` and `qdrant-client` are added to `pyproject.toml`; `docker-compose.yml` gains dev-only `opensearch` and `qdrant` services. Indexes are derived: rolling back means dropping the indexes/collections and the `index_sync_state` rows; PostgreSQL and the vault are untouched.

## Open Questions

- **Embedding model and vector dimension.** The documented default is BGE-M3 at 1024 dimensions, already set in `.env.example` and matching the Qdrant collection size. Build-plan open question 1 raises a smaller English-only model (BGE-small-en / GTE-small) to cut memory. This fixes the Qdrant collection dimension, so it should be confirmed at phase start; the plan recommends keeping BGE-M3 / 1024.
- **Drain UX.** The plan proposes an explicit `compendium index sync` plus inline `reindex`, with no synchronous drain at the end of ingest. To confirm at the review gate.
