## Context

This change implements Phase 10 (golden dataset and testing, workstream J) of `docs/COMPENDIUM_BUILD.md` — the final phase. It depends on all prior phases and follows `docs/Compendium.md` Part V (the testing strategy and golden-dataset definition). The Phase 0–9 suite already covers Layers 1–3 and 5 (unit, integration, pipeline, graph) with 72 passing tests; Phase 10 adds Layer 4 (golden) and the CI that runs the layers.

The design's full golden dataset (≤12 curated sources, query categories A–E, 3-job CI, testcontainers) is the v0.2+ target. The build-plan scope for v0.1 is a small hermetic golden dataset over the existing fixtures plus GitHub Actions CI, sized so nightly completes in tens of seconds and the dataset stays reviewable by hand.

## Goals / Non-Goals

**Goals:**

- A fixed, reviewable golden dataset (YAML) measuring retrieval quality on the existing fixtures, hermetically (stub embedder).
- A golden runner that seeds deterministically, runs each query through the real pipeline, and asserts expectations.
- A regression detector: breaking the ranker trips a golden assertion (the verbatim acceptance check).
- CI on GitHub Actions: the suite on every push/PR; the full golden suite nightly.

**Non-Goals:**

- The larger curated golden corpus and query categories B (cross-source synthesis) and E (filter-respecting) — deferred; v0.1 covers A/C/D, which the current corpus and retrieval support.
- Real-embedding semantic quality eval (manual, per Part V "not tested in v0.1").
- Load/perf tests; automated TUI-rendering tests; a testcontainers refactor (CI service containers provide the stores; the existing skip-if-unreachable fixtures run as-is).
- Any schema migration or production code change.

## Decisions

### Decision: the golden dataset is a YAML manifest over the existing fixtures

`tests/golden/dataset.yaml` lists queries, each with `id`, `category` (A/C/D), `query`, optional `filters`, and `expectations` (`top_k`, `must_include_slug`, `must_include_in_top`, `coverage_min`, `fallback_to_chunks`, and for D an `expansion_slug` that must appear via the fast loop). Pages are addressed by **slug**, not UUID — slugs are stable across reseeds, whereas the design's example UUIDs are not. The corpus is the current `tests/fixtures/` (`sample.md/pdf/epub/html`), so no new content to author; the manifest is the authoritative spec and a thin loader parses it.

**Alternative considered:** UUID-keyed expectations (per the design's YAML example) — rejected because ids change every reseed, making the manifest non-portable; slugs are deterministic from titles.

### Decision: deterministic, hermetic seeding with the stub embedder

The golden runner builds a fixed corpus state in a dedicated `compendium_golden` database: ingest the fixtures, synthesize the expected concept page(s), `reindex all`, `graph rebuild` — all under `COMPENDIUM_EMBED_STUB`/`COMPENDIUM_SYNTH_STUB`. The stub embedder is deterministic, so dense retrieval is stable (if not semantically meaningful); golden assertions therefore target what is stable: the BM25-driven top page (Category A), the `fallback_to_chunks`/`gaps` flags (Category C), and a graph-expansion candidate reached via a seeded `RELATED_TO`/`PREREQUISITE_FOR` edge (Category D). Real-embedding quality remains a manual exercise. Seeding mirrors the integration fixtures and skips when a store is unreachable.

### Decision: assertions are top-K membership and flags, not exact rank

Category A asserts the expected slug is within `top_k` (default 3) and, where specified, in the top `must_include_in_top`; it does not assert an exact position, because RRF ties and stub-dense noise make exact rank brittle. Category C asserts `fallback_to_chunks` is true and `gaps` is non-empty. Category D seeds a semantic edge, then asserts the expansion target appears in the final ranking and `query_traces.graph_expansion` records it. Coverage floors (`coverage_min`) are asserted only where the corpus makes them stable.

### Decision: the regression detector monkeypatches the ranker in-test

The detector (a test) runs the golden set once to confirm it passes, then monkeypatches the fusion/coverage path to a broken ranker (e.g. `reciprocal_rank_fusion` returning an empty or reversed list) and asserts that at least one golden expectation now fails. This proves the golden suite detects a real regression — the literal acceptance criterion — without shipping any production toggle. It is marked slow/golden so it runs in the nightly tier.

### Decision: pytest markers split the tiers; CI uses service containers

Add markers in `pyproject.toml`: `golden` (the golden suite + regression detector) and `integration` (tests needing live stores). CI (`.github/workflows/ci.yml`) has two jobs, both starting Postgres/OpenSearch/Qdrant/Memgraph as **service containers** (matching `docker-compose.yml`: OpenSearch single-node security-disabled, the remapped ports irrelevant inside CI since services bind standard ports) with `COMPENDIUM_EMBED_STUB=1`:

- `test` — on push and PR: `uv run pytest` of everything except the slow golden regression detector (i.e. unit + integration + pipeline + graph + a golden smoke). Target a few minutes.
- `nightly` — scheduled (cron) on main: the full golden suite including the regression detector.

The existing fixtures connect to the configured stores and skip when unreachable, so they need no change; CI simply provides reachable stores. `act` can run the workflow locally for offline development.

## Risks / Trade-offs

- **Stub embeddings mean golden measures pipeline + lexical stability, not semantic quality** → Accepted and explicit: real-embedding quality is a manual nightly/ad-hoc exercise (Part V). The hermetic golden still catches ranker/pipeline/fallback/expansion regressions, which is its job in CI.
- **CI service containers (esp. OpenSearch) are heavy and can be flaky on startup** → Health-check/wait steps before tests; OpenSearch pinned to the compose image and config; keep the per-push tier lean.
- **Golden assertions could be too strict (flaky) or too loose (toothless)** → Top-K membership + flags (not exact rank) for robustness; the regression detector guarantees they are not toothless.
- **Slug-keyed expectations break if a fixture's title changes** → Acceptable: fixtures are fixed test data; a title change is a deliberate dataset edit.

## Migration Plan

No schema migration, no runtime dependency. Add `tests/golden/` (manifest + loader), `tests/test_golden.py`, pytest markers in `pyproject.toml`, and `.github/workflows/ci.yml`. Rollback is deleting those files and the marker config; nothing in the application or prior phases changes.

## Open Questions

- **Query categories in scope.** The plan implements A (direct), C (fallback), and D (expansion). Confirm B (cross-source synthesis) and E (filters) are deferred — they need a richer corpus and query-time filter support not built in v0.1.
- **Nightly trigger.** A `schedule:` cron on `main` plus `workflow_dispatch` for on-demand. Confirm that is the desired nightly mechanism (versus only on-demand) at the review gate.
