# Phase 4 — Derived indexes (OpenSearch + Qdrant): Implementation Plan

Date: 2026-05-24
Branch: `phase-4-derived-indexes` (off `main`)
OpenSpec change: `openspec/changes/phase-4-derived-indexes/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 4;
[docs/Compendium.md](../docs/Compendium.md) ADR-005, § OpenSearch indexes, § Qdrant collections.

## Goal

OpenSearch and Qdrant are populated from PostgreSQL and the vault, sync state is tracked in `index_sync_state`, and `compendium reindex` produces a deterministic rebuild from empty.

## Why this plan exists

It locks in how Compendium derives its two search indexes from the system of record: page body comes from the canonical vault file while structured fields come from `wiki_pages`; embedding is an injectable seam so tests and later eval run offline; writes enqueue sync rows and an explicit command drains them; and rebuild determinism is verified per store (byte-stable for OpenSearch, top-K Jaccard for Qdrant's nondeterministic HNSW). Without these decisions fixed, retrieval (Phase 5) would be built on indexes whose freshness, content source, and rebuildability are ambiguous.

## Branch + commit strategy

- Create `phase-4-derived-indexes` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 4a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 4 complete — derived indexes`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan and smoke test pass. The user reviews and merges.

## Sub-phases

### 4a — Backing stores, clients, dependencies

**Purpose:** Stand up OpenSearch and Qdrant locally and connect to them from config.

**Tasks:**

1. Add dev-only `opensearch` (single-node, security disabled) and `qdrant` services to `docker-compose.yml`, ports `9200` and `6333`.
2. Add `opensearch-py` and `qdrant-client` to `pyproject.toml`; refresh `uv.lock`.
3. `compendium/index/clients.py`: build the OpenSearch and Qdrant clients from `OPENSEARCH_URL` / `QDRANT_URL`, with a reachability ping helper used by tests to skip.

**Files added:** `compendium/index/clients.py`
**Files modified:** `docker-compose.yml`, `pyproject.toml`, `uv.lock`

**Decision flagged:** OpenSearch dev service runs with the security plugin disabled (single-user local dev only), matching the existing Postgres dev posture.

### 4b — Embedding seam

**Purpose:** Produce 1024-dim vectors through a seam that is real in production and deterministic in tests.

**Tasks:**

1. `compendium/index/embedder.py`: an `Embedder` protocol — embed a batch of texts to 1024-dim vectors.
2. Real adapter: OpenAI-compatible embeddings call to `EMBED_MODEL` at `EMBEDDINGS_ENDPOINT` via the existing `openai` SDK.
3. Deterministic stub adapter (hash-seeded fixed-dimension vectors); `get_embedder()` returns the stub under `COMPENDIUM_EMBED_STUB`, else the real adapter.

**Files added:** `compendium/index/embedder.py`
**Files modified:** none

**Decision flagged:** Mirrors Phase 3's `Synthesizer` seam and `COMPENDIUM_SYNTH_STUB`. This is also the seam Phase 10 eval reuses for a cached/replay embedder.

### 4c — Index schemas and document projection

**Purpose:** Create the index/collection schemas and project entities into documents.

**Tasks:**

1. `compendium/index/opensearch.py`: create/delete the `pages` and `chunks` indexes with the documented analyzers and strict mappings; upsert/delete a document by `_id`; count.
2. `compendium/index/qdrant.py`: create/recreate the `pages` and `chunks` collections (1024-dim Cosine, documented HNSW params, payload indexes); upsert/delete points by id; count.
3. `compendium/index/documents.py`: project a page (structured fields from `wiki_pages`, body parsed from the vault file at `file_path`) and a chunk (from `chunks` + denormalized `sources.title`) into the OpenSearch document and the Qdrant payload.

**Files added:** `compendium/index/opensearch.py`, `compendium/index/qdrant.py`, `compendium/index/documents.py`
**Files modified:** none

**Decision flagged:** Page body comes from the canonical vault file (ADR-001); structured fields from PostgreSQL. Chunks are pure PostgreSQL. This realizes "rebuildable from PostgreSQL plus the vault."

### 4d — Sync enqueue and worker

**Purpose:** Enqueue sync rows on every write and drain them into both indexes.

**Tasks:**

1. Extend `compendium/db/repository.py`: enqueue `index_sync_state` (idempotent reset to `pending` via the unique constraint), claim pending rows (ordered, partial-index-backed), mark `indexed` / `failed` with `last_error` and `attempts`, count by `index_kind` and `state`.
2. Enqueue hooks: `vault.write_page` enqueues `opensearch_pages` + `qdrant_pages` inside the write transaction; the chunk-insert path in `compendium/ingest/pipeline.py` enqueues `opensearch_chunks` + `qdrant_chunks`.
3. `compendium/index/sync.py`: drain pending rows — load entity, project, embed for Qdrant, upsert by UUID, mark `indexed`; on exception record `last_error` / `attempts` and mark `failed`.

**Files added:** `compendium/index/sync.py`
**Files modified:** `compendium/db/repository.py`, `compendium/wiki/vault.py`, `compendium/ingest/pipeline.py`

**Decision flagged:** Enqueue happens inside the existing write transaction; draining is a separate explicit step (no always-on worker in v0.1).

### 4e — Reindex and CLI

**Purpose:** Operator commands to rebuild, drain, and inspect the indexes.

**Tasks:**

1. `compendium reindex {pages|chunks|all}`: drop + recreate the target schema and repopulate deterministically from PostgreSQL plus the vault.
2. `compendium index sync`: drain the pending queue.
3. `compendium index status`: per-index document counts and the `index_sync_state` pending/indexed/failed breakdown (reads `v_sync_lag`).

**Files added:** none
**Files modified:** `compendium/__main__.py`

**Decision flagged:** none.

### 4f — Tests, smoke, acceptance

**Purpose:** Prove population, drain, and deterministic rebuild.

**Tasks:**

1. Unit tests: document projection shapes, stub-embedder determinism, enqueue idempotency.
2. Integration tests (skip if OpenSearch/Qdrant unreachable; stub embedder): ingest fixtures, drain, assert counts, run a known OpenSearch and Qdrant query, assert a relevant hit.
3. Rebuild test: drop indexes, `reindex all`, assert counts restored and a known query's top result stable (OpenSearch byte-stable; Qdrant top-K IDs within a small Jaccard distance).
4. Append the Phase 4 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/test_indexes.py`
**Files modified:** `tests/manual/smoke_test.md`

**Decision flagged:** Integration tests default to the stub embedder so they do not require Docker Model Runner.

## Final file tree after Phase 4

```text
compendium/
  index/
    __init__.py
    clients.py        (new)
    embedder.py       (new)
    opensearch.py     (new)
    qdrant.py         (new)
    documents.py      (new)
    sync.py           (new)
  db/
    repository.py     (modified — index_sync_state functions)
  wiki/
    vault.py          (modified — enqueue page sync rows)
  ingest/
    pipeline.py       (modified — enqueue chunk sync rows)
  __main__.py         (modified — reindex / index subcommands)
docker-compose.yml    (modified — opensearch, qdrant services)
pyproject.toml        (modified — opensearch-py, qdrant-client)
uv.lock               (modified)
tests/
  test_indexes.py     (new)
  manual/smoke_test.md (modified — § Phase 4)
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | Page projection | OpenSearch doc and Qdrant payload carry the documented fields; body matches the vault file |
| 2 | unit | Chunk projection | doc/payload carry `source_id`, `source_title`, `position`, `body` |
| 3 | unit | Stub embedder | same text → identical 1024-dim vector, no network |
| 4 | unit | Enqueue idempotency | re-enqueuing an `indexed` entity resets its rows to `pending` |
| 5 | integration | Drain populates both indexes | after ingest + `index sync`, OpenSearch and Qdrant counts equal page/chunk counts; rows `indexed` |
| 6 | integration | Known query returns relevant hit | an OpenSearch `body` search and a Qdrant ANN search each return the expected page |
| 7 | pipeline | Deterministic rebuild | drop + `reindex all` restores counts; known query top result stable (Qdrant top-K Jaccard) |

## Per-phase smoke test

The scenarios appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 4 on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 4.1 | Stores up | `docker compose up -d opensearch qdrant` | both reachable: `curl :9200` and `curl :6333/collections` respond |
| 4.2 | Schemas created | `uv run python -m compendium reindex all` (empty corpus ok) | `pages`/`chunks` index and collections exist |
| 4.3 | Populate | ingest the three fixtures, `uv run python -m compendium index sync` | `index status` shows pending 0, indexed = page+chunk count |
| 4.4 | OpenSearch query | `GET /pages/_search` for a known term | a relevant page in the hits |
| 4.5 | Qdrant query | `POST /collections/pages/points/search` with an embedded query | a relevant page point returned |
| 4.6 | Rebuild | drop indexes, `reindex all` | counts restored; the 4.4 query returns the same top page |

## Out of scope for Phase 4 (do NOT build)

- Retrieval, RRF fusion, coverage scoring, chunk fallback (Phase 5).
- Memgraph and the `memgraph` index kind (Phase 6).
- An always-on background sync daemon or scheduler (Phase 8 / later).
- pgvector and `query_traces.query_embedding` persistence (Phase 5/7).
- Analyzer/boost tuning against the golden dataset (Phase 10).

## Open questions to confirm before starting

1. **Embedding model and vector dimension.** Keep the documented default BGE-M3 / 1024 (already in `.env.example`, matches the Qdrant schema), or switch now to a smaller English-only model (BGE-small-en / GTE-small) to cut memory? This fixes the Qdrant collection dimension. **Recommendation: keep BGE-M3 / 1024.**
2. **Drain UX.** Confirm the explicit-drain model: writes enqueue, `compendium index sync` drains, `reindex` repopulates inline, and ingestion does not drain synchronously. **Recommendation: explicit drain (eventual consistency, fast ingest).**

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 4 met.
- [ ] PR marked ready for review.
