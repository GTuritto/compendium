# Retrieval tuning

Operational reference for `tests/golden/baseline.json`, the
`--golden-baseline` regeneration flag, and the v0.2 Phase 5
tuning loop. v0.2 Phase 5 added measurable retrieval quality
signals; this document is how the curator drives the loop
forward as the corpus grows and as later phases (LLM-rewriting
in Phase 6, autonomous edges in Phase 8) reshape what the
indexes see.

## Metrics

Three per-query metrics, captured per golden query and
aggregated per category and overall.

| Metric | Definition |
| --- | --- |
| `coverage_score` | The `query_traces.coverage_score` value — the normalized top-page coverage signal from v0.1 Phase 5 (the original retrieval pipeline). Always populated. |
| `recall_at_k` | `1.0` when the expectation's `must_include_slug` appears in the first `K` final-ranking entries; `0.0` otherwise. `K = retrieval.top_k` from `config/settings.yaml` (default 7). `null` when the expectation has no `must_include_slug` (Categories C, D). |
| `MRR` | `1.0 / rank` where rank is the 1-indexed position of `must_include_slug` in the top-K; `0.0` when not in top-K; `null` when no `must_include_slug`. |

Aggregates (per-category and overall) compute the mean over
queries where the metric is defined. `null` values are excluded,
not coerced to 0 — Category C/D queries do not drag the recall@K
/ MRR means.

## Reading `baseline.json`

The file at `tests/golden/baseline.json` carries the captured
numbers under the current branch's analyzer + HNSW + query
normalizer. The shape is:

```json
{
  "per_query": { "<query_id>": {"coverage_score": ..., "recall_at_k": ..., "mrr": ...}, ... },
  "by_category": { "A": {...}, "C": {...}, "D": {...} },
  "overall": {...}
}
```

The file is committed. PRs that intentionally change ranking
quality must regenerate it (and explain the deltas in the PR
body).

## Regenerating the baseline

```sh
COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 \
  uv run pytest -m golden --golden-baseline -q
```

The `--golden-baseline` flag (added in `tests/conftest.py`)
switches `test_golden_baseline` from "compare to file" to
"write file from live run". Without the flag the same test
loads the file, runs the suite, and prints any per-query or
aggregate metric drift exceeding `BASELINE_TOLERANCE` (`0.01`
absolute) — informationally, not as a gated assertion. The
strict gate becomes enforceable once the metric variance drops;
see the "When MRR flaps" note below.

## The tuning loop

The Phase 5 tuning loop is **operator-driven, not automated**.
The loop benefits from human judgment about which deltas matter;
an automated runner would make destructive index changes the
operator may not want to commit.

```sh
# 1. Save the current baseline as the "before" snapshot.
cp tests/golden/baseline.json /tmp/baseline.before.json

# 2. Change one or more knobs:
#    - OpenSearch: compendium/index/opensearch.py — analyzer chain,
#      filter parameters.
#    - Qdrant HNSW: compendium/index/qdrant.py — m, ef_construct,
#      and the SEARCH_PARAMS.hnsw_ef constant.
#    - Synonyms: compendium/index/synonyms.py — the line format
#      itself (one-directional vs bidirectional, etc.).
#    - Query normalizer: compendium/retrieve/normalize.py — the
#      STOP_WORDS set, the alias-expansion ordering.

# 3. Rebuild the indexes so the analyzer and HNSW config pick up
#    the change (synonyms regenerate automatically on reindex).
COMPENDIUM_EMBED_STUB=1 uv run python -m compendium reindex all

# 4. Capture the new baseline.
COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 \
  uv run pytest -m golden --golden-baseline -q

# 5. Compare. Eyeball the per-query and aggregate deltas:
diff /tmp/baseline.before.json tests/golden/baseline.json

# 6. Accept or revert. If at least two of the three metric
#    aggregates moved up AND no per-query assertion in
#    `test_golden_dataset` regresses, commit the change. Otherwise
#    revert the source change and try a different parameter set.
```

The per-query semantic gate (`test_golden_dataset` — the v0.1
acceptance, `must_include_slug` in `top_k`) is the hard stop.
The metric aggregates are the directional signal.

## The synonyms pipeline

```
wiki_pages.aliases (concept rows)
        │
        │  compendium/index/synonyms.py::generate_synonyms(conn)
        ▼
list[str] — one OpenSearch synonym filter line per concept
        │
        │  compendium/index/sync.py::_reindex() passes the list
        ▼
opensearch.recreate_index(... synonyms=lines)
        │
        ▼
analyzer chain: lowercase → asciifolding → compendium_synonyms → english_stop → english_stemmer
```

The synonyms are **inline** in the OpenSearch analyzer config,
not file-based. The reindex helper regenerates the lines on every
`compendium reindex pages` and `reindex all`, so a new concept
alias propagates on the next reindex.

When `compendium index sync` runs (the incremental sync path,
not a full reindex), the existing analyzer keeps its current
synonyms. To pick up a new alias without a full reindex, run
`compendium reindex pages` after adding it.

Format of each line, post-resolved-decision #3:

```
alias_a, alias_b => Canonical Title
```

One-directional: the analyzer expands aliases to the canonical
title; queries containing the canonical do NOT match documents
that carry only an alias (a deliberate precision trade-off).
Aliases are deduped case-insensitively; aliases equal to the
canonical title are skipped.

## Stop-words

The query normalizer (`compendium/retrieve/normalize.py`)
strips a small curated English stop-word set before alias
expansion:

```
a, an, and, are, at, but, for, from, in, is, of, on, or, the, to
```

Conservative — drops obvious function words without risking a
meaningful term. The OpenSearch analyzer separately applies its
own `_english_` stop-words at index time; the normalizer's list
is a reasonable subset.

Per resolved decision #4, the order is **lowercase → stop-words
→ alias expansion**. Stripping `the` before the alias check
keeps "the psych safety concept" matchable as "psych safety
concept" → "psychological safety concept".

## Stop-words and alias-expansion ordering

```
"The Psychological Safety concept"
        │ lowercase
        ▼
"the psychological safety concept"
        │ strip stop-words (the)
        ▼
"psychological safety concept"
        │ alias expansion (no match — already canonical)
        ▼
"psychological safety concept"   ← what hits the indexes


"psych safety"
        │ lowercase
        ▼
"psych safety"
        │ strip stop-words (no stop-words)
        ▼
"psych safety"
        │ alias expansion (whole-query match)
        ▼
"psychological safety"           ← what hits the indexes
```

## When a metric flatlines

When tuning iterations stop moving the aggregates, options to
consider — in roughly increasing complexity order:

1. **Bigger / different golden dataset.** v0.2 Phase 5 ships a
   4-query manifest plus the alias-match demonstration; recall@K
   saturates at 1.0 because the corpus is small. Add queries
   where the must_include_slug is not in the top-2 by default
   to give recall@K and MRR more to chew on.
2. **Reduce `K`.** Edit `retrieval.top_k` in `config/settings.yaml`
   from 7 down to 3 or 5; the golden runner picks up the new K
   automatically. This makes recall@K and MRR more sensitive to
   ranking changes.
3. **Edge n-grams in the analyzer.** Added as a filter step
   before the synonym filter, edge n-grams trade index size
   for partial-match recall. Optional per the build plan;
   add only if the corpus has frequent partial-term queries.
4. **BM25 `k1` / `b` tuning.** OpenSearch's BM25 similarity
   takes `k1` (term-frequency saturation) and `b` (length
   normalization) parameters. Defaults work for most corpora;
   move only after the simpler levers above stop helping.
5. **Dense reranking.** Lands in Phase 6's `ask` as part of
   the LLM-composed answer; not a Phase 5 lever.
6. **Live-tier golden** with real BGE-M3 embeddings instead of
   the stub. Defers until the cost-vs-signal trade-off is worth
   it; the hermetic golden is the day-to-day signal.

## When MRR flaps

Qdrant's HNSW insertion order is non-deterministic across
reindex cycles. On a small corpus, this lets a close-scoring
page trade rank-1 for rank-2 across consecutive identical runs,
which flips per-query MRR between `1.0` and `0.5`. v0.2 Phase 5
sets explicit HNSW parameters (`m=16, ef_construct=128,
hnsw_ef=64`) but the parameter knobs do not control the
insertion order itself.

What this means in practice:

- The `test_golden_dataset` per-query semantic assertions
  (`must_include_slug` in `top_k`) are robust at `top_k=3` or
  larger — they pass consistently across runs.
- The `test_golden_baseline` aggregate comparison is
  informational only in v0.2 Phase 5. Deltas exceeding `0.01`
  absolute print to test output but do not fail the suite.
- `coverage_score` is stable; treat it as the primary numeric
  signal in tuning.
- `recall_at_k` is stable when `top_k` is at or above the
  rank of every must-include in every run.
- `MRR` is rank-sensitive on small datasets; treat aggregates
  as directional, not as deltas to read down to the third
  decimal place.

A v0.3 follow-up can either expand the golden dataset (more
queries → tighter aggregates) or pin Qdrant's insertion order
(custom upsert loop with deterministic batching) before the
strict aggregate gate gets re-enabled.
