## ADDED Requirements

### Requirement: Page-first query pipeline

The system SHALL answer a natural-language query with a ranked list of wiki pages. The pipeline SHALL parse the query without rewriting, embed it through the Phase 4 `Embedder` seam, retrieve from the OpenSearch `pages` index and the Qdrant `pages` collection, fuse the two ranked lists, and return the fused page list. Pages SHALL be the primary retrieval unit; chunks SHALL NOT replace pages in the result.

#### Scenario: A covered query returns ranked pages

- **WHEN** `compendium query "<text>"` runs against a seeded corpus whose wiki covers the query
- **THEN** the command returns a ranked list of wiki pages with their fused scores, ordered best first

#### Scenario: The query is embedded once through the seam

- **WHEN** a query runs with the stub embedder selected
- **THEN** the query is embedded exactly once and the same embedding is used for the Qdrant search and persisted to the trace

### Requirement: Parallel cross-store fan-out

The system SHALL issue the OpenSearch and Qdrant `pages` searches concurrently using async clients gathered with `asyncio.gather`. When chunk fallback is triggered, the OpenSearch and Qdrant `chunks` searches SHALL likewise run concurrently. PostgreSQL access SHALL remain synchronous.

#### Scenario: The two page searches run concurrently

- **WHEN** the pipeline retrieves the `pages` candidates
- **THEN** the OpenSearch and Qdrant searches are dispatched together and awaited as a group, not sequentially

### Requirement: Reciprocal rank fusion

The system SHALL fuse the OpenSearch and Qdrant ranked lists with reciprocal rank fusion. Each candidate's fused score SHALL be the sum over the retrievers that returned it of `1 / (rrf_k + rank)`, where `rank` is the candidate's 1-based position in that retriever's list and `rrf_k` is the configured `retrieval.rrf_k` (default 60). A candidate present in only one retriever's list SHALL still receive a fused score from that list.

#### Scenario: A candidate ranked by both retrievers outranks one ranked by one

- **WHEN** page A is returned by both retrievers and page B by only one, at comparable ranks
- **THEN** page A receives the higher fused score

#### Scenario: Fusion is deterministic for a fixed corpus revision

- **WHEN** the same query runs twice against an unchanged corpus
- **THEN** the fused ranking is identical both times

### Requirement: Page coverage score

The system SHALL compute a page coverage score by min-max normalizing the fused page scores to the range 0–1 and taking the mean of the top-`retrieval.top_k` (default 7) normalized scores. An empty page list SHALL yield a coverage score of 0.

#### Scenario: Coverage is bounded and threshold-comparable

- **WHEN** the fused page list is scored
- **THEN** the coverage score is a value in 0–1 that can be compared directly to `retrieval.page_coverage_threshold`

#### Scenario: No pages yields zero coverage

- **WHEN** neither retriever returns any page
- **THEN** the coverage score is 0

### Requirement: Chunk fallback on thin coverage

When the page coverage score is below `retrieval.page_coverage_threshold` (default 0.5), the system SHALL additionally retrieve from the OpenSearch and Qdrant `chunks` indexes, fuse them, and attach the top chunk citations to the response. The ranked page list SHALL still be returned; chunk citations SHALL be additive, not a replacement.

#### Scenario: Low coverage attaches chunk citations

- **WHEN** a query's page coverage is below the threshold
- **THEN** the response includes chunk citations alongside the (possibly thin) page list

#### Scenario: Sufficient coverage skips chunk retrieval

- **WHEN** a query's page coverage is at or above the threshold
- **THEN** the `chunks` indexes are not queried and no chunk citations are attached

### Requirement: Gap flagging

When chunk fallback is triggered, the system SHALL set `query_traces.fallback_to_chunks` to true and append a structured gap entry to `query_traces.gaps` recording the low-coverage condition, the query, the coverage score, and the threshold.

#### Scenario: An uncovered query flags a gap

- **WHEN** a query for a topic the corpus does not cover returns coverage below the threshold
- **THEN** the persisted trace has `fallback_to_chunks = true` and a non-empty `gaps` array describing the low-coverage gap

### Requirement: Query-trace persistence

Every query SHALL persist exactly one `query_traces` row, regardless of outcome. The row SHALL record the resolved corpus revision, the query text, the embedding model and the query embedding (`REAL[]`), the per-stage candidates (`pipeline`), the final ranking (`final_ranking`), the per-stage latencies (`latencies_ms`), the coverage score, the `fallback_to_chunks` flag, and the gaps. The `graph_expansion` column SHALL be left null in this phase.

#### Scenario: A successful query writes a complete trace

- **WHEN** a query completes
- **THEN** a `query_traces` row exists containing the per-stage candidates, the fused final ranking, per-stage latencies, the coverage score, and the query embedding

#### Scenario: A zero-result query is still traced

- **WHEN** a query returns no pages
- **THEN** a `query_traces` row is still written, with an empty final ranking and coverage 0

#### Scenario: Graph expansion is not populated

- **WHEN** any query completes in this phase
- **THEN** the trace's `graph_expansion` column is null

### Requirement: The query CLI command

The system SHALL provide a `compendium query "<text>"` subcommand that runs the pipeline, prints the ranked pages with their scores and any chunk citations, and persists the trace. The command SHALL support a `--json` flag for machine-readable output and a `--top-k` override of the configured default.

#### Scenario: The command prints ranked pages and persists a trace

- **WHEN** `compendium query "<text>"` runs
- **THEN** it prints the ranked pages with scores and exits 0, and a corresponding `query_traces` row is persisted

#### Scenario: JSON output mode

- **WHEN** `compendium query "<text>" --json` runs
- **THEN** the command emits a machine-readable JSON object containing the ranked pages, coverage score, fallback flag, and citations
