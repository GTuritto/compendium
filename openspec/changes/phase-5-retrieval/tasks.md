# Tasks — phase-5-retrieval

Implements Phase 5 of `docs/COMPENDIUM_BUILD.md`. No schema migration: the
`query_traces` table and its indexes exist from Phase 1 (migration 0009), and
the `retrieval.*` config keys exist from Phase 0. Task groups map to the
sub-phases (one commit per group, green at HEAD).

## 1. Dependency and async search clients (5a)

- [ ] 1.1 Add `httpx` to `pyproject.toml`; `uv lock`
- [ ] 1.2 `compendium/retrieve/clients.py`: construct `AsyncOpenSearch` and `AsyncQdrantClient` from config (URLs from `load_config()`), mirroring the Phase 4 sync `clients.py`; include async reachability helpers
- [ ] 1.3 `compendium/retrieve/search.py`: async `search_pages` / `search_chunks` for each store — OpenSearch `_search` against `PAGES_INDEX`/`CHUNKS_INDEX` (BM25 over the documented fields), Qdrant `search` against `PAGES_COLLECTION`/`CHUNKS_COLLECTION` (query vector, top-k); each returns an ordered list of `(entity_id, score, source_fields)`

## 2. Fusion and coverage (5b)

- [ ] 2.1 `compendium/retrieve/fusion.py`: pure `reciprocal_rank_fusion(lists, rrf_k)` returning a fused ordered list with summed `1/(rrf_k+rank)` scores; a candidate in one list still scores
- [ ] 2.2 `compendium/retrieve/coverage.py`: pure `coverage_score(fused_scores, top_k)` — min-max normalize to 0–1, mean of the top-`top_k`; 0 for empty, handle single-result and all-equal degenerate cases

## 3. Pipeline orchestrator and trace assembly (5c)

- [ ] 3.1 `compendium/retrieve/pipeline.py`: orchestrate ADR-003 — embed the query (Phase 4 `Embedder`), `asyncio.gather` the two `pages` searches, RRF-fuse, compute coverage; if coverage `< page_coverage_threshold`, gather the two `chunks` searches, fuse, attach citations, set `fallback_to_chunks`, append a structured `gaps` entry
- [ ] 3.2 Expose both an async `run()` coroutine (for in-loop callers like the Phase 8 TUI) and a sync `query()` wrapper (`asyncio.run`) for the CLI; resolve `corpus_revision` via `repository.ensure_corpus_revision`
- [ ] 3.3 Assemble the trace payload: per-stage candidates (`pipeline`), `final_ranking`, per-stage `latencies_ms`, `coverage_score`, `fallback_to_chunks`, `gaps`, the query embedding (`REAL[]`); `graph_expansion` left null

## 4. Trace persistence (5d)

- [ ] 4.1 `compendium/db/repository.py`: `insert_query_trace(...)` — write one `query_traces` row (JSONB for `pipeline`/`final_ranking`/`latencies_ms`/`gaps`, `REAL[]` for `query_embedding`); a read helper for the CLI if needed
- [ ] 4.2 Wire trace persistence into the pipeline after the response is assembled; a zero-result query still writes a trace

## 5. Query CLI (5e)

- [ ] 5.1 `compendium query "<text>"` subcommand in `compendium/__main__.py` (argparse): run the pipeline, print ranked pages with scores and any chunk citations, persist the trace, exit 0
- [ ] 5.2 `--json` flag (machine-readable: pages, coverage score, fallback flag, citations) and a `--top-k` override of the configured default

## 6. Tests and acceptance (5f)

- [ ] 6.1 Unit tests: RRF fusion (both-vs-one, determinism), coverage scoring (bounds, empty→0, single-result, all-equal)
- [ ] 6.2 Integration tests (skip if OpenSearch/Qdrant unreachable, stub embedder): seed via Phase 3/4 fixtures, run a covered query and assert expected page titles rank top; assert the two page searches are dispatched concurrently
- [ ] 6.3 Fallback test: a query the corpus does not cover returns coverage below threshold, attaches chunk citations, and persists a trace with `fallback_to_chunks = true` and a non-empty `gaps`
- [ ] 6.4 Trace test: a successful query persists one complete `query_traces` row (candidates per stage, fused final ranking, latencies, coverage, embedding); `graph_expansion` is null
- [ ] 6.5 Append the Phase 5 smoke section to `tests/manual/smoke_test.md`; run it
- [ ] 6.6 **Acceptance:** three handcrafted queries against the seeded corpus return expected page titles; `query_traces` holds the full pipeline state per query; an uncovered query flags a gap. `uv run pytest` passes
