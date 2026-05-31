# Tasks — v0.2-phase-5-tuning

Implements v0.2 Phase 5 of `docs/COMPENDIUM_V0.2_BUILD.md`. No schema migration; no new runtime dependency. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. Baseline metrics + golden runner extension (5a)

- [ ] 1.1 `tests/golden/__init__.py`: add `compute_metrics(trace, expectation) -> dict` returning `{coverage_score, recall_at_k, mrr}` per query; aggregate to `summarize(per_query) -> dict` with overall + per-category means (excluding `null`).
- [ ] 1.2 `tests/golden/__init__.py`: `K` reads from `retrieval.top_k` in `settings.yaml`.
- [ ] 1.3 `tests/test_golden.py`: register a `--golden-baseline` pytest CLI flag; when set, the golden runner writes `tests/golden/baseline.json` from the live metrics instead of asserting against it.
- [ ] 1.4 `tests/golden/baseline.json`: capture the current numbers under the v0.1 default analyzer + HNSW defaults. Includes per-query and aggregated metrics. Committed as a fresh file.
- [ ] 1.5 `tests/test_golden.py`: a new test that loads `baseline.json`, runs the live golden suite, and asserts no metric regresses by more than `0.01` absolute against the corresponding baseline entry.
- [ ] 1.6 Unit-level: verify the per-category aggregation handles `null` recall@K / MRR (Categories C/D have no must-include slug) without dragging the mean.

## 2. Rule-based query normalization (5b)

- [ ] 2.1 `compendium/retrieve/normalize.py`: `class AliasIndex` with `from_db()`, `refresh()`, `expand(text: str) -> str`. Backed by `SELECT title, aliases FROM wiki_pages WHERE kind='concept'`.
- [ ] 2.2 `compendium/retrieve/normalize.py`: `normalize_query(text: str, alias_index: AliasIndex) -> str` performs lowercase → strip the curated stop-word set → alias expansion. Returns the normalized query string.
- [ ] 2.3 `compendium/retrieve/pipeline.py`: at the head of `query()` (before fan-out), call `normalize_query()` on the input text; persist both the raw and the normalized query on the `query_trace` row (existing `query_text` column carries the raw; add a `normalized_query` field to the trace payload or piggyback on the existing `query_embedding`-adjacent metadata column).
- [ ] 2.4 The cached `AliasIndex` instance is created lazily on first `query()` invocation and reused across calls in the same process.
- [ ] 2.5 Unit tests for `normalize_query`: lowercase ("Psychological Safety" → "psychological safety"); stop-words ("the psychological safety concept" → "psychological safety concept"); alias expansion (an alias for an existing concept → the canonical name); no-match passthrough (a query that does not hit any alias returns unchanged after lowercase+stop-words).
- [ ] 2.6 Unit tests for `AliasIndex`: lazy load (constructor does not touch the DB); `from_db()` reads the expected shape; `refresh()` re-reads.

## 3. OpenSearch analyzer + Qdrant HNSW tuning iterations (5c)

- [ ] 3.1 `compendium/index/synonyms.py`: `generate_synonyms_file(conn, output_path: Path)` — reads `wiki_pages` aliases, writes `synonyms.txt` in OpenSearch synonym filter format (one entry per line, one-directional: `alias_a, alias_b => canonical_title`).
- [ ] 3.2 `compendium/index/opensearch.py`: replace the default analyzer with `analyzer_compendium_english` (lowercase + `english_snowball` filter + `synonyms` filter pointing at the generated file). Both `pages` and `chunks` index mappings adopt it for the `body` field; `title` keeps a lighter `standard` analyzer to preserve exact-match recall on titles.
- [ ] 3.3 `compendium/index/qdrant.py`: collection create-call passes `hnsw_config=HnswConfigDiff(m=16, ef_construct=128)` as the starting point; search call passes `search_params=SearchParams(hnsw_ef=64)`.
- [ ] 3.4 Reindex helper (`compendium/index/sync.py` or `compendium/index/__init__.py`) calls `generate_synonyms_file()` before re-creating the OpenSearch index, so the new analyzer picks up the current aliases.
- [ ] 3.5 Tuning loop (operator-driven, not automated): with the v0.1-default baseline captured in 1.4, apply the analyzer + HNSW changes from 3.2 / 3.3, run `compendium reindex all`, regenerate the baseline with `--golden-baseline`, compare to the prior baseline. Iterate `m / ef_construct / ef` until at least two of the three metrics improve and no golden assertion regresses. Commit the chosen values.
- [ ] 3.6 Unit-level: verify the synonyms file generator emits the expected line format and skips concepts with no aliases.

## 4. Operational doc + smoke + acceptance close (5d)

- [ ] 4.1 `docs/operations/retrieval-tuning.md`: sections — "Metrics" (coverage / recall@K / MRR definitions; the `K` source); "Reading `baseline.json`"; "Regenerating the baseline" (the `--golden-baseline` flag); "The tuning loop" (change a parameter, reindex, regenerate, compare, accept-or-revert); "The synonyms pipeline" (how aliases flow from `wiki_pages` to `synonyms.txt` to OpenSearch); "Stop-words" (the curated list and why it is small); "When a metric flatlines" (suggested next steps — edge n-grams, BM25 `k1`/`b` tuning, dense reranking).
- [ ] 4.2 Append the Phase 5 (v0.2) smoke section to `tests/manual/smoke_test.md` with scenarios v0.2-5.1 → v0.2-5.6.
- [ ] 4.3 `README.md`: extend the v0.2 status sentence to mention Phase 5 and link to `docs/operations/retrieval-tuning.md`.
- [ ] 4.4 `CLAUDE.md`: status sentence catches up to Phase 5; v0.2 phases bullet gains a Phase 5 entry; resolved decisions note the metrics + tolerance + synonym pipeline.
- [ ] 4.5 `docs/COMPENDIUM_V0.2_BUILD.md`: Status section gains a Phase 5 merged entry.
- [ ] 4.6 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 5: per-query coverage / recall@K / MRR land in `tests/golden/baseline.json`; tuning iterations on the OpenSearch analyzer + Qdrant HNSW improve at least two of the three aggregated metrics against the v0.1-default baseline; no golden assertion regresses; query normalization is wired into `pipeline.query` and unit-tested; operational doc exists; smoke walk passes.
- [ ] 4.7 `openspec validate v0.2-phase-5-tuning` clean.
