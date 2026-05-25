# Phase 5 — Page-first retrieval: Implementation Plan

Date: 2026-05-25
Branch: `phase-5-retrieval` (off `main`)
OpenSpec change: `openspec/changes/phase-5-retrieval/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 5;
[docs/Compendium.md](../docs/Compendium.md) ADR-003.

## Goal

A query against Compendium returns a ranked list of wiki pages, with chunk
fallback when page coverage is thin, and the entire trace is persisted.

## Why this plan exists

This is the first phase that *reads* the system, and the realization of the
core bet (ADR-003): pages, not chunks, are the unit of retrieval. The plan locks
in three decisions that are expensive to change later: (1) the search fan-out is
async (`AsyncOpenSearch` + `AsyncQdrantClient` gathered with `asyncio.gather`)
while the DB stays synchronous; (2) fusion is reciprocal rank fusion on rank, not
score; (3) the coverage score is the normalized top-page mean, so the otherwise
unbounded RRF scores become comparable to the configured `0.5` threshold.
Without pinning these, the pipeline shape, the trace contents, and the fallback
trigger are all ambiguous.

## Branch + commit strategy

- Create `phase-5-retrieval` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 5a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 5 complete — page-first retrieval`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### 5a — Dependency and async search clients

**Purpose:** Stand up the async read path over the Phase 4 index schemas.

**Tasks:**

1. Add `httpx` to `pyproject.toml`; `uv lock`.
2. `compendium/retrieve/clients.py`: build `AsyncOpenSearch` and
   `AsyncQdrantClient` from config, with async reachability helpers (mirror the
   Phase 4 sync `clients.py`).
3. `compendium/retrieve/search.py`: async `search_pages` / `search_chunks` per
   store — OpenSearch `_search` (BM25 over the documented page/chunk fields),
   Qdrant vector `search`; each returns an ordered list of
   `(entity_id, score, source_fields)`.

**Files added:** `compendium/retrieve/clients.py`, `compendium/retrieve/search.py`
**Files modified:** `pyproject.toml`, `uv.lock`

**Decision flagged:** Async clients (`AsyncOpenSearch` + `AsyncQdrantClient`),
not `to_thread` over the Phase 4 sync clients and not raw httpx to the REST
endpoints. Honors the CLAUDE.md fan-out note; keeps schema knowledge in the
official clients.

### 5b — Fusion and coverage

**Purpose:** The two pure, store-free scoring functions.

**Tasks:**

1. `compendium/retrieve/fusion.py`: `reciprocal_rank_fusion(lists, rrf_k)` —
   fused score = sum over retrievers of `1/(rrf_k + rank)`, 1-based rank; a
   candidate present in one list still scores.
2. `compendium/retrieve/coverage.py`: `coverage_score(fused_scores, top_k)` —
   min-max normalize to 0–1, mean of the top-`top_k`; 0 for empty; handle
   single-result and all-equal degenerate cases.

**Files added:** `compendium/retrieve/fusion.py`, `compendium/retrieve/coverage.py`
**Files modified:** none

**Decision flagged:** RRF on rank (scale-free, ADR-003) and coverage as the
normalized top-page mean (bounded, threshold-comparable). Both user-confirmed.

### 5c — Pipeline orchestrator and trace assembly

**Purpose:** Wire ADR-003 end to end and build the trace payload.

**Tasks:**

1. `compendium/retrieve/pipeline.py`: embed query (Phase 4 `Embedder`),
   `asyncio.gather` the two `pages` searches, fuse, score coverage; if coverage
   `< page_coverage_threshold`, gather the two `chunks` searches, fuse, attach
   citations, set `fallback_to_chunks`, append a structured `gaps` entry.
2. Expose async `run()` (for in-loop callers) and a sync `query()` wrapper
   (`asyncio.run`) for the CLI; resolve `corpus_revision` via
   `repository.ensure_corpus_revision`.
3. Assemble the trace payload: `pipeline` (per-stage candidates),
   `final_ranking`, `latencies_ms`, `coverage_score`, `fallback_to_chunks`,
   `gaps`, query embedding (`REAL[]`); `graph_expansion` left null.

**Files added:** `compendium/retrieve/pipeline.py`
**Files modified:** none

**Decision flagged:** Page list is always returned; chunks are additive
citations, never a replacement. `graph_expansion` stays null in this phase.

### 5d — Trace persistence

**Purpose:** Every query writes exactly one `query_traces` row.

**Tasks:**

1. `compendium/db/repository.py`: `insert_query_trace(...)` (JSONB for
   `pipeline`/`final_ranking`/`latencies_ms`/`gaps`, `REAL[]` for
   `query_embedding`); a read helper if the CLI needs one.
2. Wire persistence into the pipeline after the response is assembled; a
   zero-result query still writes a trace.

**Files added:** none
**Files modified:** `compendium/db/repository.py`

**Decision flagged:** Trace write is synchronous and after response assembly, so
latency is not gated on the DB write but no query goes untraced.

### 5e — Query CLI

**Purpose:** The user-facing entry point.

**Tasks:**

1. `compendium query "<text>"` subcommand in `compendium/__main__.py`: run the
   pipeline, print ranked pages with scores and any chunk citations, persist the
   trace, exit 0.
2. `--json` flag (pages, coverage score, fallback flag, citations) and a
   `--top-k` override.

**Files added:** none
**Files modified:** `compendium/__main__.py`

**Decision flagged:** The command is `query`, not `ask` (`ask` is reserved for
the v0.2 composed-answer interface).

### 5f — Tests and acceptance

**Purpose:** Unit, integration, fallback, and trace coverage; smoke test.

**Tasks:**

1. Unit: RRF fusion (both-vs-one, determinism); coverage (bounds, empty→0,
   single-result, all-equal).
2. Integration (skip if stores unreachable, stub embedder): seed via Phase 3/4
   fixtures; covered query ranks expected page titles top; assert the two page
   searches dispatch concurrently.
3. Fallback: uncovered query → coverage below threshold, chunk citations
   attached, trace `fallback_to_chunks = true` with non-empty `gaps`.
4. Trace: successful query persists one complete row; `graph_expansion` null.
5. Append the Phase 5 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/test_retrieval.py` (and fixtures as needed)
**Files modified:** `tests/manual/smoke_test.md`

**Decision flagged:** none.

## Final file tree after Phase 5

```text
compendium/
  retrieve/
    __init__.py          (existing stub; gains exports)
    clients.py           NEW — AsyncOpenSearch + AsyncQdrantClient
    search.py            NEW — async per-store page/chunk search
    fusion.py            NEW — reciprocal rank fusion (pure)
    coverage.py          NEW — normalized top-page mean (pure)
    pipeline.py          NEW — ADR-003 orchestrator + trace assembly
  db/
    repository.py        MOD — insert_query_trace (+ read helper)
  __main__.py            MOD — `compendium query` subcommand
pyproject.toml           MOD — httpx
uv.lock                  MOD
tests/
  test_retrieval.py      NEW
  manual/smoke_test.md   MOD — § Phase 5
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | RRF: page in both lists vs one list | both-list page outranks one-list page; rerun identical |
| 2 | unit | Coverage: empty / single / all-equal / normal | 0 for empty; 1 for single and all-equal; in 0–1 and matches hand calc otherwise |
| 3 | integration | Covered query on seeded corpus | expected page titles rank in the top results |
| 4 | integration | Concurrency | the two `pages` searches are dispatched together (gather), not sequentially |
| 5 | pipeline | Uncovered query | coverage < threshold; chunk citations attached; page list still returned |
| 6 | pipeline | Trace completeness | one `query_traces` row with pipeline/final_ranking/latencies/coverage/embedding; `graph_expansion` null |
| 7 | pipeline | Gap flag | uncovered query → `fallback_to_chunks = true`, non-empty `gaps` |

## Per-phase smoke test

The scenarios appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md)
§ Phase 5 on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 5.1 | Covered query returns pages | `uv run python -m compendium query "<covered topic>"` | exit 0; ranked page titles printed with scores; one new `query_traces` row |
| 5.2 | JSON output | `uv run python -m compendium query "<covered topic>" --json` | exit 0; JSON with pages, `coverage_score`, `fallback_to_chunks`, citations |
| 5.3 | Uncovered query flags a gap | `uv run python -m compendium query "<topic absent from corpus>"` | exit 0; chunk citations shown; trace row has `fallback_to_chunks = true` and non-empty `gaps` |
| 5.4 | Trace inspection | `psql … -c "SELECT query_text, coverage_score, fallback_to_chunks, jsonb_array_length(gaps) FROM query_traces ORDER BY created_at DESC LIMIT 3"` | three rows matching the queries above with sane coverage/fallback values |

## Out of scope for Phase 5 (do NOT build)

- Graph expansion / the Memgraph fast loop (ADR-009) — Phase 6 + Phase 9.
  `query_traces.graph_expansion` stays null.
- Query rewriting and LLM-composed answers ("ask") — v0.2.
- Trace replay, trace inspection UI, revision diffs — Phase 7.
- The TUI ops console — Phase 8.
- Slow-loop curation signals (`graph_curation_signals`) — Phase 9.
- Any change to index schemas, the embedder, or the write/sync paths — Phase 4
  owns those; Phase 5 only reads.

## Open questions — resolved at the review gate (2026-05-25)

1. **Coverage threshold value.** RESOLVED: ship Phase 5 with
   `page_coverage_threshold = 0.5` untuned; real tuning waits for the Phase 10
   golden dataset.
2. **One `top_k` or two.** RESOLVED: keep `top_k = 7` unified for the coverage
   window and the display count; split later only if the golden dataset shows
   they want different values.
3. **Chunk-citation count on fallback.** RESOLVED: reuse `top_k` for the chunk
   citation cap.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 5 met.
- [ ] PR marked ready for review.
