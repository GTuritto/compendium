## Why

v0.1 shipped page-first retrieval with default-everything: OpenSearch's default English analyzer, Qdrant HNSW at the library's defaults, and a raw query text passed straight to BM25 + dense fan-out. The golden suite (Phase 10) proved the ranking pipeline does not regress, but it never measured how *good* retrieval is — only that it is consistent across runs. v0.2's thesis is "better answers"; Phase 5 is where the retrieval substrate gets sharpened.

Three things move in this phase:

1. **A measurable baseline.** The golden runner gains per-query `coverage_score`, `recall@K`, and `MRR` calculations and writes them to `tests/golden/baseline.json` on demand. From this commit onward, every retrieval-affecting change can be evaluated against a fixed file rather than the curator's memory.
2. **Rule-based query normalization** in `compendium/retrieve/pipeline.query()` — lowercase, English stop-words, and alias expansion against the `wiki_pages.aliases` column. This is "Shape D part 1" from the v0.2 thesis grilling round (LLM-based rewriting is absorbed into Phase 6's `ask` so the `query` hot path stays free of LLM cost).
3. **Tuning iterations** on the OpenSearch analyzer (English stemmer, synonym filter sourced from page aliases) and the Qdrant HNSW parameters (`m`, `ef_construct`, `ef`). The acceptance gate: at least two of the three metrics improve against the baseline; no golden assertion regresses (Phase 10's regression detector is the contract).

The fourth thing — an operational document at `docs/operations/retrieval-tuning.md` — codifies the tuning loop so the curator can re-run it after Phase 6 / 7 / 8 ship.

## What Changes

- **Golden runner metrics extension.** `tests/golden/__init__.py` gains per-query metric computation: `coverage_score` (from the existing trace), `recall@K` (was the must-include slug in the top-K?), and `MRR` (1 / rank of the first must-include slug, or 0 if not found). A summary aggregates per-category and overall.
- **Baseline file.** `tests/golden/baseline.json` carries the current numbers, regenerated via `uv run pytest -m golden --golden-baseline` (a new pytest flag, no new CLI verb). The default golden run compares the live metrics against the baseline and fails when any metric regresses by more than a small tolerance (`0.01` absolute).
- **Rule-based query normalizer.** A new `compendium/retrieve/normalize.py` exposes `normalize_query(text, alias_index) -> str`. Wired into `compendium/retrieve/pipeline.py` before the BM25 + dense fan-out. Lowercase. Strip English stop-words (a small curated list — no new dependency). Alias expansion via a cached `AliasIndex` loaded lazily from `wiki_pages.aliases`.
- **OpenSearch analyzer tuning.** `compendium/index/opensearch.py` index creation switches to a custom analyzer: lowercase + English Snowball stemmer + a synonym filter sourced from a `synonyms.txt` file generated at reindex time from `wiki_pages.aliases`. The synonyms file regenerates on every `compendium reindex pages` (and `reindex all`) so it stays current with the corpus.
- **Qdrant HNSW tuning.** `compendium/index/qdrant.py` collection creation gains explicit HNSW parameters (`m`, `ef_construct`); search calls pass `hnsw_ef` (`ef`). Default values picked from the golden run; the tuning loop in 5c iterates and picks the best-improving config.
- **An operational document** `docs/operations/retrieval-tuning.md` covering: the metric definitions and how to read `baseline.json`; the tuning loop (change a parameter, regenerate, compare); the synonym-file generator and how aliases flow into OpenSearch; the regression-detector gate; suggested next steps when one of the three metrics flatlines.
- **A Phase 5 (v0.2) smoke section** appended to `tests/manual/smoke_test.md` with scenarios v0.2-5.1 → v0.2-5.6.
- **Tests.** Unit tests for `normalize_query` (lowercase, stop-words, alias expansion, no-match passthrough). Unit tests for `AliasIndex` (lazy load, miss-returns-input, multi-alias collapse). Golden-suite assertions in `tests/test_golden.py` that compare live metrics to `baseline.json` with the small tolerance. Integration test that exercises the full normalize → fan-out → fuse → rank path against a populated test DB.

## Capabilities

### New Capabilities

- `retrieval-tuning`: per-query metric extension on the golden runner; `tests/golden/baseline.json` and the `--golden-baseline` regeneration flag; rule-based query normalization (`compendium/retrieve/normalize.py` + the `AliasIndex` cache); OpenSearch English-Snowball + synonym-filter analyzer; Qdrant HNSW parameters; `docs/operations/retrieval-tuning.md`; the golden assertions that compare live metrics to baseline within tolerance.

### Modified Capabilities

<!-- The v0.1 page-first retrieval contract (RRF fusion, top-page
coverage, chunk fallback, trace persistence) is preserved. The
v0.2 Phase 5 changes are: (a) what runs before fan-out (query
normalization); (b) how the OpenSearch index tokenizes
(analyzer); (c) how the Qdrant index searches (HNSW ef); (d) what
the golden suite measures (metrics). No public API changes;
the existing `compendium query` CLI behaviour is unchanged at
the contract level — only its ranking quality moves. -->

## Impact

- **New code/files:** `compendium/retrieve/normalize.py` (the normalizer + `AliasIndex`); `tests/golden/baseline.json`; `docs/operations/retrieval-tuning.md`.
- **Modified files:** `compendium/retrieve/pipeline.py` (wire normalizer at the head of the fan-out); `compendium/index/opensearch.py` (analyzer + synonym filter); `compendium/index/qdrant.py` (HNSW config + `hnsw_ef` search); `compendium/index/sync.py` or a new `compendium/index/synonyms.py` for the `synonyms.txt` generator; `tests/golden/__init__.py` (per-query metric computation); `tests/test_golden.py` (baseline comparison + regenerate flag); `tests/manual/smoke_test.md` (new § Phase 5 (v0.2)); `README.md` (one-line pointer); `CLAUDE.md` (v0.2 Phase 5 status + decisions); `docs/COMPENDIUM_V0.2_BUILD.md` Status section (Phase 5 merged entry).
- **No schema migration.** Reads existing `wiki_pages.aliases`. No new tables.
- **No new runtime dependency.** OpenSearch's `snowball` token filter and `synonym` token filter ship with every OpenSearch distribution. Qdrant HNSW parameters are first-class in the existing `qdrant-client` API.
- **No new CLI verb.** Baseline regeneration is a pytest flag (`--golden-baseline`); query normalization is internal to `compendium query`; tuning iterations are operator-driven via the documented tuning loop.
- **CI impact.** The hermetic suite is unchanged in shape; the golden tier now compares against `baseline.json`. The baseline file is checked into the repo; PRs that change ranking quality must regenerate it (and explain the delta in the PR body).
- **Out of scope:**
  - **LLM-based query rewriting.** Lands in Phase 6 inside `compendium ask` so the `query` hot path stays free of LLM cost.
  - **Edge n-grams** in the OpenSearch analyzer. Optional per the build plan; deferred unless the metric needs it.
  - **A separate live-tier golden** with real embeddings. The hermetic golden is what gates Phase 5; the real-embedding tier was deferred in Phase 10 and stays deferred here.
  - **Per-query analyzer overrides.** One analyzer for the whole `pages` index; same for `chunks`.
  - **Learning-to-rank** or ranker training. RRF stays as the fusion ranker.
  - **A TUI screen for the tuning loop.** CLI + operational doc only.
