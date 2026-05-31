## Context

This change implements Phase 5 of `docs/COMPENDIUM_V0.2_BUILD.md`. It depends on the v0.1 retrieval pipeline (`compendium/retrieve/pipeline.py`), the v0.1 OpenSearch + Qdrant index modules, and the Phase 10 golden suite (`tests/golden/`). It does not depend on later v0.2 phases.

The retrieval substrate has been frozen at library defaults since v0.1 Phase 4 shipped. The golden suite ensures it does not regress; Phase 5 is the first time we measure whether it is *good*. The three deliverables — baseline metrics, query normalization, analyzer + HNSW tuning — are independent commits but read as a single improvement story: we measured, we normalized the input, we sharpened the indexes; the golden numbers moved.

## Goals / Non-Goals

**Goals:**

- A `tests/golden/baseline.json` capturing per-query `coverage_score`, `recall@K`, and `MRR` plus per-category and overall aggregates. Regenerable on demand; otherwise immutable and committed to the repo.
- Rule-based query normalization in the `query` hot path: lowercase, English stop-words, alias expansion against `wiki_pages.aliases`. Zero LLM cost on the hot path.
- An OpenSearch analyzer that uses the English Snowball stemmer and a synonym filter sourced from page aliases. The synonyms file regenerates on every reindex.
- Qdrant HNSW parameters (`m`, `ef_construct`, `hnsw_ef`) configured deliberately, with the tuning loop documented and the chosen values picked from the golden runs.
- An operational document the curator follows to re-run the tuning loop after future phases ship.

**Non-Goals:**

- LLM-based query rewriting (Phase 6's `ask`).
- A separate live-tier golden with real embeddings (deferred from Phase 10; still deferred).
- Edge n-grams in the OpenSearch analyzer (optional per the build plan; gate on metric need).
- Per-query analyzer overrides.
- Learning-to-rank, ranker training, or non-RRF fusion strategies.
- TUI integration for the tuning loop.
- A new CLI verb for the tuning loop (it is a documented operator workflow + a pytest flag).

## Decisions

### Decision: baseline regeneration is a pytest flag, not a CLI verb

`uv run pytest -m golden --golden-baseline` writes `tests/golden/baseline.json` from the current run. Default golden runs (without the flag) load the file and compare per-query metrics to it. The flag avoids a new top-level CLI verb (`compendium golden baseline ...`) for what is fundamentally a test-harness operation.

**Alternative considered:** a `compendium golden baseline` CLI verb. Rejected — the golden harness already lives inside pytest; a CLI wrapper would duplicate setup code and confuse the boundary between "user-facing" verbs and "developer/test" tooling.

### Decision: metric definitions

- **`coverage_score`** — read directly from `query_traces.coverage_score` (the normalized top-page coverage v0.1 Phase 5 already computes). No new math.
- **`recall@K`** — for a Category A query with `must_include_slug=X`, recall@K is 1.0 if X appears in the top-`K` results, else 0.0. `K` is `retrieval.top_k` from `settings.yaml` (default 7). For categories without a must-include slug (e.g., Category C fallback queries), recall@K is reported as `null`.
- **`MRR`** — for a Category A query with `must_include_slug=X`, MRR is `1.0 / rank` where rank is the 1-indexed position of X in the ranking (or 0.0 if X is not in the top-K). Category C/D queries report MRR as `null`.
- **Aggregates** — overall and per-category means computed only over queries where the metric is defined (i.e., excluding `null`).

**Alternative considered:** include precision, NDCG, etc. Rejected — Phase 5's gate is "improve ≥2 of 3"; adding more metrics dilutes the signal and adds maintenance surface. The three above are well-aligned with the actual retrieval contract (coverage, top-K membership, rank quality).

### Decision: tolerance is `0.01` absolute

A live run that drops a metric by more than `0.01` against baseline triggers a test failure ("retrieval regression"). The tolerance accounts for small stochastic effects (RRF ties broken by sort order, etc.) while keeping the gate meaningful.

**Alternative considered:** relative tolerance (e.g., 5%). Rejected — absolute matches the metric units (0..1) and is easier to reason about. A 0.01 absolute tolerance on a 0.78 coverage allows up to 1.3% relative drop; on a 0.50 coverage it allows 2%.

### Decision: synonym filter sourced from `wiki_pages.aliases`

OpenSearch's `synonym` token filter consumes a `synonyms.txt` file with one entry per line in `comma_separated_aliases, canonical` form (or `=>` syntax). The `compendium/index/synonyms.py` generator queries `SELECT title, aliases FROM wiki_pages WHERE kind='concept' AND status IN ('canonical', 'draft')` and writes the file to a deterministic path that OpenSearch reads at index-creation time. The file regenerates on every `compendium reindex pages` and `compendium reindex all`; it is *not* live-reloadable (OpenSearch synonym updates require an index restart in the default config).

**Alternative considered:** the live-reloadable `synonym_graph` filter with `updateable=true`. Rejected — adds an extra index-refresh API call and is sensitive to multi-shard timing; with a single-node OpenSearch and per-reindex regeneration, the simpler `synonym` filter is enough. A v0.3 phase can switch when the corpus grows beyond what a per-reindex rebuild can handle.

### Decision: Qdrant HNSW tuning is iterative; the chosen values are committed in code

The tuning loop runs the golden suite with a candidate `(m, ef_construct, ef)` triple, compares the resulting baseline to the prior baseline, accepts on `>=2/3` improvement with no golden assertion regression, otherwise reverts. The accepted values land as constants in `compendium/index/qdrant.py`; the operational doc describes how to re-run the loop after a corpus change.

Starting point for the loop: `m=16`, `ef_construct=128`, `hnsw_ef=64` (more aggressive than qdrant-client defaults, but not unusual). These will be the post-Phase-5 commit's values unless the tuning loop in 5c finds better.

**Alternative considered:** ship a `compendium tune` CLI verb that automates the loop. Rejected — the loop is short (a handful of parameter sets), benefits from human judgment ("this triple regressed Category C but improved A"), and would be misleading as an automated job because it makes destructive index changes.

### Decision: stop-word list is a small curated set, not Snowball's

The query normalizer's stop-word filter uses a hand-curated list (`the`, `a`, `an`, `and`, `or`, `but`, `of`, `for`, `in`, `on`, `at`, `to`, `from`, `is`, `are`). Short, conservative, and uncontroversial — it removes obvious noise without risking a meaningful term getting dropped. OpenSearch's analyzer separately applies its own English stop-words at index time; the query normalizer's list mirrors a reasonable subset.

**Alternative considered:** import `nltk` or `spacy` stop-words. Rejected — neither is in the dependency tree; adding one for fifteen words is not worth the surface area.

### Decision: `AliasIndex` is loaded lazily and cached per-process

The normalizer needs a reverse index from alias → canonical title (or slug). `AliasIndex.from_db()` runs one `SELECT title, aliases FROM wiki_pages WHERE kind='concept'` query and builds the dict. The instance is cached in a module-level variable and refreshed only on explicit `AliasIndex.refresh()` calls. In a long-running daemon (Phase 7+) the refresh can be wired to the slow loop; in the v0.2 Phase 5 short-lived CLI invocation, one load per `compendium query` is fine.

**Alternative considered:** load on every query without caching. Rejected — Postgres is fast but a redundant query per-CLI-invocation is wasteful. The lazy-cache pattern matches the existing `compendium.config.load_config()` shape.

## Risks / Trade-offs

- **The hermetic golden is on stub embeddings.** Dense retrieval ranking against stub vectors is essentially BM25-driven (dense scores are random within a fixed seed). Tuning Qdrant HNSW for the stub vectors does not predict real-embedding behaviour. Mitigated by also running the live-models golden walk after the analyzer / synonym changes; that walk is not part of the v0.2 Phase 5 acceptance but is the smoke verification for the curator.
- **Synonym filter applied at index time means re-ingesting after adding aliases requires a reindex.** The operational doc names this explicitly. A v0.3 phase can move to `synonym_graph` with `updateable=true` if alias churn becomes a problem in practice.
- **Stop-word lists drop signal in non-English contexts.** v0.2 stays English-first. The curated list is conservative; the OpenSearch analyzer's stop-words are configurable per-index if a future phase needs to relax them.
- **`AliasIndex` staleness in long-running processes.** v0.2 Phase 5 CLI invocations are short-lived; in Phase 7's `serve` daemon this becomes a real concern. A refresh hook on slow-loop end (Phase 7+ work) keeps the index current; v0.2 Phase 5 ships the cache + manual `refresh()` only.
- **Baseline regressions after a synth that adds new aliases.** A new alias enters `wiki_pages.aliases` → the next reindex generates a new `synonyms.txt` → the OpenSearch index tokens for matching docs change. This can shift recall@K up or down for golden queries that relied on the prior tokenization. The remedy: re-run with `--golden-baseline` to update the baseline, then explain the delta in the PR body that introduced the alias.

## Migration Plan

No schema migration, no data destruction. The OpenSearch index needs to be re-created with the new analyzer (existing indexes do not gain a new analyzer in-place); `compendium reindex pages` and `reindex all` already drop-and-rebuild, so a single `reindex all` on the curator's host applies the Phase 5 analyzer + the regenerated `synonyms.txt`. Qdrant collections likewise re-create with the new HNSW config on reindex.

Rollback is removing the new code, reverting `pipeline.py` / `opensearch.py` / `qdrant.py` changes, deleting the operational doc and `baseline.json`. The pre-Phase-5 ranking quality returns on the next reindex.

## Open Questions

- **Tolerance value.** `0.01` absolute is the proposal. Recommendation: confirm. A future phase can tighten as the corpus grows and metrics stabilize.
- **Are synonyms one-directional (alias → canonical) or bidirectional?** OpenSearch's `synonym` filter accepts both. Recommendation: one-directional (`alias_a, alias_b => canonical`) so the canonical token always wins. Bidirectional would let queries containing the canonical match documents that only have an alias — a more permissive recall but a harder precision story.
- **Should the normalizer drop stop-words BEFORE alias expansion or AFTER?** If "psychological safety" is a canonical name and "the psychological safety concept" is the query, stripping `the` first lets the alias-expansion check `psychological safety concept` which would not match. Recommendation: stop-words first (drop "the" → "psychological safety concept"), then alias expansion (no match → return as-is). The risk: a future alias `the X` would never match. Acceptable; aliases are normally noun phrases.
- **Where does `synonyms.txt` live on disk?** OpenSearch needs a path it can read at index-creation time. Recommendation: a sub-path under the OpenSearch container's config dir, mounted from the host's `./synonyms/` (gitignored). The reindex helper writes the file before issuing the index-create call.
- **Qdrant HNSW starting parameters.** Proposal: `m=16, ef_construct=128, hnsw_ef=64`. Recommendation: confirm as the starting point for the tuning loop; the loop in 5c may move them.
