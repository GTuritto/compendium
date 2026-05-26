## ADDED Requirements

### Requirement: Golden dataset manifest

The system SHALL define a golden dataset as a YAML manifest of queries over a fixed corpus. Each entry SHALL carry an `id`, a `category` (A direct retrieval, C fallback/gap, or D graph-expansion), the `query` text, optional `filters`, and `expectations`. Pages in expectations SHALL be addressed by slug (stable across reseeds), not by generated UUID.

#### Scenario: The manifest loads and is well-formed

- **WHEN** the golden loader parses the manifest
- **THEN** every entry has an id, a known category, a query, and an expectations block, and the loader exposes them to the runner

### Requirement: Deterministic hermetic seeding

The golden runner SHALL build a fixed corpus state (ingest the fixtures, synthesize the expected concept page(s), reindex, and rebuild the graph) using the deterministic stub embedder and stub synthesizer, requiring no external embeddings endpoint. It SHALL skip when a required backing store is unreachable.

#### Scenario: Seeding is reproducible without a model endpoint

- **WHEN** the golden runner seeds the corpus with the stub embedder
- **THEN** the corpus, indexes, and graph are populated deterministically and no embeddings endpoint is contacted

### Requirement: Golden quality assertions

The runner SHALL run each manifest query through the retrieval pipeline and assert its expectations: Category A asserts the expected page slug appears within `top_k`; Category C asserts the trace's `fallback_to_chunks` is set and `gaps` is non-empty; Category D asserts an expansion candidate (reached via a seeded semantic edge) appears in the final ranking and is recorded in `query_traces.graph_expansion`.

#### Scenario: A direct-retrieval query returns its expected page

- **WHEN** a Category A query runs against the seeded corpus
- **THEN** the expected page slug is within the top-K results

#### Scenario: A fallback query flags the gap

- **WHEN** a Category C query runs
- **THEN** the trace has `fallback_to_chunks` true and a non-empty `gaps`

#### Scenario: A graph-expansion query surfaces the expanded page

- **WHEN** a Category D query runs against a corpus with the seeded semantic edge
- **THEN** the expansion target appears in the ranking and in the trace's `graph_expansion`

### Requirement: Regression detector

The system SHALL include a check that, after confirming the golden set passes, injects a deliberate ranker break (e.g. disabling reciprocal rank fusion) and asserts that at least one golden expectation then fails. The break SHALL be a test-only injection, not a production toggle.

#### Scenario: Breaking the ranker trips a golden assertion

- **WHEN** the page-first ranker is deliberately broken and the golden set re-runs
- **THEN** at least one golden expectation fails (the suite detects the regression)

### Requirement: Layered suite and CI

The test suite SHALL be marked so it can run in tiers: a fast tier (unit + integration + pipeline + graph + a golden smoke) and the full golden suite. CI on GitHub Actions SHALL run the fast tier on every push and pull request with the four backing stores available as service containers and the stub embedder, and SHALL run the full golden suite (including the regression detector) on a nightly schedule.

#### Scenario: The full suite runs

- **WHEN** `uv run pytest` runs with the backing stores available
- **THEN** the full suite executes, including the golden tests

#### Scenario: CI runs the fast tier on push

- **WHEN** a commit is pushed
- **THEN** the CI `test` job starts the backing stores and runs the fast tier to completion

#### Scenario: Nightly runs the full golden suite

- **WHEN** the scheduled nightly job runs on main
- **THEN** it executes the full golden suite including the regression detector
