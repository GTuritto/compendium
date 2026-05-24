# Tasks — phase-4-derived-indexes

Implements Phase 4 of `docs/COMPENDIUM_BUILD.md`. No schema migration: the
`index_sync_state` table and the `index_kind` / `sync_state` enums exist from
Phase 1.

## 1. Backing stores, clients, dependencies (4a)

- [ ] 1.1 Add dev-only `opensearch` and `qdrant` services to `docker-compose.yml`
- [ ] 1.2 Add `opensearch-py` and `qdrant-client` to `pyproject.toml`; `uv lock`
- [ ] 1.3 `compendium/index/clients.py`: construct the OpenSearch and Qdrant clients from config, with a reachability ping

## 2. Embedding seam (4b)

- [ ] 2.1 `compendium/index/embedder.py`: an `Embedder` protocol (embed a batch of texts to 1024-dim vectors)
- [ ] 2.2 Real adapter: OpenAI-compatible embeddings call to `EMBED_MODEL` at `EMBEDDINGS_ENDPOINT` via the `openai` SDK
- [ ] 2.3 Deterministic stub adapter (hash-seeded fixed vectors); `get_embedder()` selects the stub under `COMPENDIUM_EMBED_STUB`, else the real adapter

## 3. Index schemas and document projection (4c)

- [ ] 3.1 `compendium/index/opensearch.py`: create/delete the `pages` and `chunks` indexes (documented analyzers + strict mappings); upsert/delete a document by `_id`; count
- [ ] 3.2 `compendium/index/qdrant.py`: create/recreate the `pages` and `chunks` collections (1024-dim Cosine, HNSW params, payload indexes); upsert/delete points by id; count
- [ ] 3.3 `compendium/index/documents.py`: project a page (fields from `wiki_pages`, body from the vault file) and a chunk (from `chunks` + `sources.title`) into the OpenSearch document and Qdrant payload

## 4. Sync enqueue and worker (4d)

- [ ] 4.1 Extend `compendium/db/repository.py`: enqueue `index_sync_state` (idempotent reset to `pending`), claim pending rows, mark `indexed`/`failed`, count by index_kind and state
- [ ] 4.2 Enqueue hooks: page writes (`compendium/wiki/vault.py`) enqueue `opensearch_pages` + `qdrant_pages`; chunk writes (`compendium/ingest/pipeline.py`) enqueue `opensearch_chunks` + `qdrant_chunks`
- [ ] 4.3 `compendium/index/sync.py`: drain pending rows — load entity, project, embed for Qdrant, upsert, mark `indexed`; on error record `last_error`/`attempts` and mark `failed`

## 5. Reindex and CLI (4e)

- [ ] 5.1 `compendium reindex {pages|chunks|all}`: drop + recreate the target schema and repopulate deterministically from PostgreSQL plus the vault
- [ ] 5.2 `compendium index sync`: drain the pending queue
- [ ] 5.3 `compendium index status`: per-index document counts and `index_sync_state` pending/indexed/failed breakdown

## 6. Tests and acceptance (4f)

- [ ] 6.1 Unit tests: document projection (page and chunk doc/payload shapes), stub embedder determinism, enqueue idempotency
- [ ] 6.2 Integration tests (skip if OpenSearch/Qdrant unreachable, stub embedder): ingest fixtures, drain, assert counts, run a known OpenSearch and Qdrant query and assert a relevant hit
- [ ] 6.3 Rebuild test: drop indexes, `reindex all`, assert counts restored and a known query's top result stable (OpenSearch byte-stable; Qdrant top-K IDs within Jaccard distance)
- [ ] 6.4 Append the Phase 4 smoke section to `tests/manual/smoke_test.md`; run it
- [ ] 6.5 **Acceptance:** after Phase 3's ingest, both indexes contain the expected counts; an OpenSearch (`GET /pages/_search`) and a Qdrant (`/collections/pages/points/search`) query each return relevant results; `compendium reindex all` from empty restores the same state. `uv run pytest` passes
