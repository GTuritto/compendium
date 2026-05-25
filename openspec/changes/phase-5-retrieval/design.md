## Context

This change implements Phase 5 (page-first retrieval) of `docs/COMPENDIUM_BUILD.md`. It is the first phase that reads the system rather than building it. It builds on the Phase 4 derived indexes (the `pages` and `chunks` OpenSearch indexes and Qdrant collections, the `Embedder` seam), the Phase 1 schema (`query_traces`, migration 0009), the Phase 0 config loader (`retrieval.rrf_k`, `retrieval.page_coverage_threshold`, `retrieval.top_k` in `config/settings.yaml`), and `repository.ensure_corpus_revision()`.

ADR-003 is the governing decision: retrieval is page-first. Queries resolve to wiki pages ranked by a hybrid of OpenSearch (BM25) and Qdrant (dense) scores fused with reciprocal rank fusion, with chunks as a fallback only when page coverage is below a threshold. The pipeline shape (parse, embed, fan out, fuse, score coverage, branch on coverage) is specified there step by step and is implemented faithfully.

The architectural constraint that shapes the most code: PostgreSQL access stays synchronous `psycopg 3` (CLAUDE.md), but the cross-store search fan-out to OpenSearch and Qdrant is parallel via `asyncio.gather`.

## Goals / Non-Goals

**Goals:**

- A `compendium query "<text>"` returns a ranked list of wiki pages with scores and chunk citations.
- The two `pages` searches (OpenSearch + Qdrant) run concurrently; on fallback, the two `chunks` searches do too.
- Page coverage is a bounded, threshold-comparable score; below threshold triggers chunk fallback and a gap flag.
- Every query persists a complete `query_traces` row: candidates per stage, fusion, fallback, final ranking, per-stage latencies, coverage, and gaps.

**Non-Goals:**

- Graph expansion / the Memgraph fast loop (ADR-009). `query_traces.graph_expansion` stays null in Phase 5; expansion lands in Phase 6/9.
- Query rewriting and LLM-composed answers (v0.2). Phase 5 returns ranked pages, not prose.
- Trace replay, trace inspection UI, and revision diffs (Phase 7).
- The TUI (Phase 8) and slow-loop curation signals (Phase 9).
- Any change to the index schemas, the embedder, or the write/sync paths (Phase 4 owns those).

## Decisions

### Decision: async httpx-backed clients for the search fan-out

The retrieval pipeline issues the two `pages` searches (and, on fallback, the two `chunks` searches) concurrently with `asyncio.gather`, using `AsyncOpenSearch` (from `opensearch-py`) and `AsyncQdrantClient` (from `qdrant-client`, httpx transport). This honors the CLAUDE.md note that "Phase 5's parallel fan-out uses httpx + asyncio.gather, independent of the DB layer." The DB layer stays synchronous `psycopg 3`; the orchestrator embeds the query (a single synchronous `Embedder` call), runs the async fan-out under `asyncio.run` (the CLI is synchronous), and writes the trace synchronously after. Phase 4's synchronous `opensearch-py` / `qdrant-client` indexing clients are untouched; Phase 5 adds an async **query** path beside them.

**Alternatives considered:** wrapping the Phase 4 sync clients in `asyncio.to_thread` (reuses one client family but uses threads, not the documented httpx async path); hand-written `httpx` calls against the raw `_search` / `points/search` REST endpoints (re-encodes index knowledge outside the Phase 4 modules). The async official clients keep the field/schema knowledge in one place while matching the documented async fan-out.

### Decision: reciprocal rank fusion over rank, not score

The two retrievers return incomparable score scales (BM25 relevance vs. cosine similarity). RRF fuses on **rank**: each candidate's fused score is the sum over retrievers of `1 / (rrf_k + rank)`, with `rrf_k` from config (default 60) and `rank` 1-based within each retriever's result list. A candidate missing from one retriever simply contributes nothing from that retriever. This is parameter-light, scale-free, and reproducible for a fixed corpus revision.

**Alternatives considered:** weighted score normalization and linear combination (requires per-retriever score calibration that drifts with corpus size); CombSUM/CombMNZ over normalized scores (more sensitive to outlier scores than RRF). RRF is the ADR-003 choice.

### Decision: coverage = normalized top-page mean

RRF fused scores are unbounded sums, not comparable to the configured `page_coverage_threshold` of 0.5. The coverage score min-max normalizes the fused page scores into 0–1 (best fused page → 1, worst → 0) and takes the **mean of the top-`top_k`** normalized scores. This is bounded, directly comparable to the threshold, and rewards a cluster of strong pages over a single lucky hit. Edge cases: zero pages → coverage 0 (fallback); a single page → that page normalizes to 1, coverage 1 (no fallback), which is acceptable because one strong page is real coverage; all-equal scores → all normalize to 1.

**Alternatives considered:** the single best page's normalized score (a lone strong hit masks a thin result); averaging pre-fusion raw similarities from the dense side only (couples coverage to one retriever and ignores lexical agreement). The normalized top-page mean was the user-confirmed choice.

### Decision: coverage is computed, then the pipeline branches once

Coverage is computed on the fused `pages` list. If coverage ≥ threshold, the pipeline returns the page list and writes the trace (`fallback_to_chunks = false`, `gaps = []`). If coverage < threshold, the pipeline fans out to the two `chunks` indexes, fuses them, attaches the top chunk citations to the response, sets `fallback_to_chunks = true`, and appends a structured gap (`{kind: "low_coverage", query, coverage_score, threshold}`) to `gaps`. The page list is always returned; chunks are additive citations, never a replacement, preserving page-first semantics.

### Decision: the trace is assembled in one place and persisted synchronously

A single trace assembler collects each stage's output (OpenSearch hits, Qdrant hits, RRF-fused list, coverage, fallback chunk hits if any), the per-stage wall-clock latencies, the query embedding, and the resolved `corpus_revision`, and `repository.insert_query_trace` writes one row. `pipeline`, `final_ranking`, `latencies_ms`, and `gaps` are JSONB; `query_embedding` is `REAL[]` (pgvector deferred — vector search lives in Qdrant). Tracing is not optional: a query that returns zero pages still writes a trace. The trace write happens after the response is assembled so retrieval latency is not gated on the DB write, but within the same command so no query goes untraced.

### Decision: stub embedder and store-reachability gating for tests

Retrieval reuses the Phase 4 `Embedder` seam, so integration tests select the deterministic stub embedder (`COMPENDIUM_EMBED_STUB`) and need no Docker Model Runner. Integration tests that need OpenSearch/Qdrant skip when those stores are unreachable, mirroring the Phase 4 pattern. Fusion, coverage scoring, and gap flagging are pure functions and are unit-tested without any store.

### Decision: `compendium query`, not `ask`

The CLI subcommand is `compendium query "<text>"` with an optional `--json` flag and a `--top-k` override. The name `ask` is reserved for the v0.2 LLM-composed-answer interface; using it now would mislabel a page-list command as an answer command.

## Risks / Trade-offs

- **Eventual consistency: a query right after a write can miss new content** → Accepted per ADR-005. The pipeline is defensive about staleness and the trace records the `corpus_revision` it ran against; the operator drains `compendium index sync` before relying on freshness.
- **Coverage threshold is unvalidated until the golden dataset (Phase 10)** → Accepted. 0.5 is a starting value; the normalized-top-page-mean formula is monotonic and explainable, and the threshold is a single config knob to tune against the Phase 10 golden set.
- **Min-max normalization is degenerate for one result or all-equal scores** → Handled explicitly (single page → coverage 1; all-equal → all 1; zero pages → coverage 0) and covered by unit tests.
- **A second (async) client path beside Phase 4's sync clients** → Accepted and bounded: the async clients are used only for read/search; indexing and reindex keep the sync clients. Both read the same Phase 4 index/collection names and field mappings.
- **`asyncio.run` inside a synchronous CLI** → Fine for a one-shot command. If a future caller is already inside an event loop (the Phase 8 TUI), it will call the async pipeline coroutine directly rather than through the `asyncio.run` wrapper; the orchestrator exposes both.

## Migration Plan

No schema migration. `query_traces` and its indexes exist from Phase 1; retrieval config exists from Phase 0. Add `httpx` to `pyproject.toml` and `uv lock`. Rollback is removing `compendium/retrieve/`, the `query` CLI subcommand, the `insert_query_trace` repository function, and the `httpx` dependency; nothing in PostgreSQL, the vault, or the indexes is altered.

## Open Questions

- **Coverage threshold value (0.5).** Kept as the documented default for Phase 5; real tuning waits for the Phase 10 golden dataset. Confirm at the review gate that shipping with 0.5 untuned is acceptable.
- **Default result count.** `top_k = 7` (matches "three to seven pages" in the design narrative) is both the coverage window and the default display count. Confirm the same value should serve both, or split into `coverage_k` vs `display_k`.
