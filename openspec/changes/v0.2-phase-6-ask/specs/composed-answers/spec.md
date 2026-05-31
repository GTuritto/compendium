## ADDED Requirements

### Requirement: `compendium ask` returns a structured, page-anchored answer

The system SHALL provide a `compendium ask "<question>"` CLI verb that returns a structured response with the fields `answer`, `refused`, `citations`, `coverage_score`, `trace_id`, `ask_trace_id`, and `gap`. Each citation SHALL carry `ref`, `slug`, `title`, and `trace_rank`. The answer SHALL be composed by an LLM over the top-K pages returned by `compendium.retrieve.pipeline.query()`; the citations SHALL reference those pages. The LLM composition call SHALL use the same `SYNTHESIS_*` configuration as `compendium synth`. The verb SHALL accept `--format text|json`.

#### Scenario: A covered question returns an answer with citations

- **GIVEN** a populated wiki whose pages cover the question, with `coverage_score` at or above `ask.refuse_below_coverage`
- **WHEN** `compendium ask "<covered question>"` runs
- **THEN** `answer` is non-null, `refused` is `false`, and `citations` contains at least one entry whose `slug`, `title`, and `trace_rank` reference a page from the retrieval result

#### Scenario: The answer is composed over the retrieval result, not a separate path

- **WHEN** `compendium ask` composes an answer
- **THEN** it composes over the pages returned by `pipeline.query()` for the (rewritten) question, and the `ask_traces` row references the same retrieval via `query_trace_id`

### Requirement: `ask` refuses below the coverage threshold

When the `coverage_score` of the retrieval result is below `ask.refuse_below_coverage` (default `0.3`), the system SHALL NOT make a composition LLM call. In that case `answer` SHALL be `null`, `refused` SHALL be `true`, `gap` SHALL be populated with the under-covered facet, and `suggested_actions` SHALL name the natural next CLI command. Refusal SHALL NOT be reported as an error (the CLI exit code is `0`).

#### Scenario: An uncovered question is refused with suggested actions

- **GIVEN** a question whose retrieval `coverage_score` is below `0.3`
- **WHEN** `compendium ask "<uncovered question>"` runs
- **THEN** `answer` is `null`, `refused` is `true`, `gap` is populated, `suggested_actions` is non-empty, no composition LLM call is made, and the process exits `0`

#### Scenario: Suggested actions name the next CLI command

- **GIVEN** a refusal where no pages cover the question
- **WHEN** the response is rendered
- **THEN** `suggested_actions` contains a copy-paste-ready CLI command (an `ingest` command when no covering pages exist; a `synth concept` command when pages exist but coverage is thin)

### Requirement: The `ask` prompt's first step is an LLM query rewrite

The system SHALL, when `ask.rewrite` is `true` (the default), rewrite the question via one LLM call into a retrieval-friendly query before calling `pipeline.query()`. The rewritten text SHALL drive retrieval; the original question SHALL drive composition. When `ask.rewrite` is `false`, the question SHALL pass through unchanged. The rewrite SHALL be part of the `ask` flow only; `compendium query` SHALL NOT perform an LLM rewrite.

#### Scenario: The query is rewritten before retrieval

- **GIVEN** `ask.rewrite` is `true`
- **WHEN** `compendium ask "<question>"` runs
- **THEN** an LLM rewrite produces the retrieval query, `pipeline.query()` is called with the rewritten text, and the rewrite is recorded on the `ask_traces` row

#### Scenario: Rewrite disabled is a passthrough

- **GIVEN** `ask.rewrite` is `false`
- **WHEN** `compendium ask "<question>"` runs
- **THEN** no rewrite LLM call is made and `pipeline.query()` receives the original question (after the existing Phase 5 rule-based normalization)

### Requirement: Every `ask` writes an `ask_traces` row joined to `query_traces`

The system SHALL persist one `ask_traces` row per `compendium ask` invocation. The row SHALL carry `query_trace_id` referencing the `query_traces` row produced by the retrieval, the `prompt_template_id`, the `model`, the `endpoint`, the `input_tokens`, the `output_tokens`, a `cost_estimate`, the `answer_text`, and `refused`. A refusal SHALL still write an `ask_traces` row with `refused=true` and a `null` answer. The `ask_traces` table SHALL be created by migration `0012` with `down_revision = "0011"`.

#### Scenario: A composed answer writes a joined ask trace

- **WHEN** `compendium ask` returns a composed answer
- **THEN** an `ask_traces` row exists with `refused=false`, the prompt template id, model, endpoint, token counts, a cost estimate, the answer text, and a `query_trace_id` that joins to the retrieval's `query_traces` row

#### Scenario: A refusal still writes an ask trace

- **WHEN** `compendium ask` refuses
- **THEN** an `ask_traces` row exists with `refused=true`, `answer_text` null, and a `query_trace_id` joining to the retrieval's `query_traces` row

#### Scenario: Migration 0012 round-trips

- **WHEN** the migration suite upgrades to `0012` and then downgrades by one
- **THEN** `ask_traces` is created with the documented columns and FK on upgrade and dropped on downgrade

### Requirement: `ask` streams its answer for interactive CLI use

In `--format text` mode the system SHALL stream the composed answer to stdout as tokens arrive, then print the citations, coverage, and trace ids. In `--format json` mode the system SHALL buffer the full answer and emit a single structured object. A refused `ask` SHALL print the structured refusal without streaming.

#### Scenario: Text mode streams the answer

- **WHEN** `compendium ask "<covered question>" --format text` runs interactively
- **THEN** the answer text streams to stdout as it is composed, followed by the citation block and trace ids

#### Scenario: JSON mode emits a single object

- **WHEN** `compendium ask "<question>" --format json` runs
- **THEN** stdout carries exactly one JSON object with the full `AskResult` fields

### Requirement: An operational document describes the `ask` composer

The repository SHALL include `docs/operations/ask.md` covering: the composer flow (rewrite → query → compose); the refusal contract (the threshold, `gap`, `suggested_actions`); the citation shape and `trace_rank`; reading an `ask_traces` row and its join to `query_traces`; the cost-estimate method and where the rate table lives; and streaming behaviour. `tests/manual/smoke_test.md` SHALL include a Phase 6 (v0.2) section covering a covered question, an uncovered (refused) question, and inspecting the `ask_traces` row.

#### Scenario: The operational doc covers the required sections

- **WHEN** the curator reads `docs/operations/ask.md` after Phase 6 merges
- **THEN** the document explains the composer flow, the refusal contract, the citation shape, reading an `ask_traces` row, the cost estimate, and streaming

#### Scenario: The smoke walk exercises `ask` end-to-end

- **WHEN** the operator walks the Phase 6 (v0.2) smoke section
- **THEN** they ask a covered question (an answer with citations), ask an uncovered question (a refusal with suggested actions), and inspect the `ask_traces` row in PostgreSQL
