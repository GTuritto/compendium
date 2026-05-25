## Why

Phases 1–4 ingest sources, synthesize the wiki, and populate the OpenSearch and Qdrant derived indexes, but nothing reads them: there is no way to ask Compendium a question. Phase 5 is the first user-visible payoff and the system's core bet (ADR-003): a query resolves to a ranked list of wiki **pages** with citations, hybrid-retrieved from BM25 + dense and fused, with chunks as a fallback only when page coverage is thin. Every query persists a full trace, which is the substrate Phases 7–9 (replay, telemetry, curation) build on.

## What Changes

- A page-first retrieval pipeline (`compendium/retrieve/`) implementing ADR-003: parse the query (no rewriting in v0.1), embed it via the Phase 4 `Embedder` seam, fan out to the OpenSearch and Qdrant `pages` indexes in parallel, fuse with reciprocal rank fusion (`rrf_k`, default 60), compute a page coverage score, and return the fused page list.
- **Parallel fan-out via async httpx-backed clients.** Querying uses `AsyncOpenSearch` and `AsyncQdrantClient` gathered with `asyncio.gather`. The PostgreSQL layer stays synchronous `psycopg 3`; only the cross-store search fan-out is async. Phase 4's synchronous index/reindex clients are untouched.
- **Coverage scoring and chunk fallback.** Coverage = the mean of the top-`top_k` (default 7) fused page scores after min-max normalization to 0–1. When coverage is below `page_coverage_threshold` (default 0.5), the pipeline also fans out to the `chunks` indexes, fuses, surfaces chunk citations alongside the page list, sets `fallback_to_chunks`, and writes a structured gap to `query_traces.gaps`.
- **Full query-trace persistence.** Every query writes a `query_traces` row: parsed query, embedding model and vector (`REAL[]`), per-stage candidates (`pipeline`), the `final_ranking`, per-stage `latencies_ms`, `coverage_score`, `fallback_to_chunks`, and `gaps`. The `graph_expansion` column stays null in v0.1.
- A `compendium query "<text>"` CLI subcommand that runs the pipeline, prints the ranked pages with scores and citations (with an optional `--json` mode), and persists the trace.

## Capabilities

### New Capabilities

- `retrieval`: Page-first hybrid retrieval — query embedding, parallel OpenSearch + Qdrant fan-out, reciprocal rank fusion, normalized top-page coverage scoring, chunk fallback with gap flagging, query-trace persistence, and the `compendium query` CLI.

### Modified Capabilities

<!-- None. The query_traces table and the retrieval config already exist (Phase 1
/ Phase 0); the Phase 4 index schemas and embedder seam are consumed as-is. No
existing capability's requirements change. -->

## Impact

- **New code:** `compendium/retrieve/` — async search clients over the Phase 4 index schemas, the RRF fuser, the coverage scorer, the pipeline orchestrator, and trace assembly. A `compendium query` CLI subcommand in `compendium/__main__.py`.
- **New repository functions:** `insert_query_trace` (and any read helper the CLI needs), persisting the `REAL[]` embedding and the JSONB `pipeline` / `final_ranking` / `latencies_ms` / `gaps` payloads to `query_traces`.
- **New dependency:** `httpx` (the async client transport; `AsyncOpenSearch` and `AsyncQdrantClient` ship with the already-present `opensearch-py` and `qdrant-client`). Query embedding reuses the existing `openai`-SDK `Embedder`.
- **No schema migration.** `query_traces` and its indexes exist from Phase 1 (migration 0009); `query_embedding` is `REAL[]` (pgvector deferred). Retrieval parameters (`rrf_k`, `page_coverage_threshold`, `top_k`) already exist in `config/settings.yaml`.
- **Out of scope** (later phases): graph expansion / Memgraph fast loop (Phase 6, 9), query rewriting and composed answers (v0.2), trace replay and revision diffs (Phase 7), the TUI (Phase 8), and slow-loop curation signals (Phase 9).
