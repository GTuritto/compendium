## ADDED Requirements

### Requirement: Composition is a public, database-free function

The system SHALL provide `compose_answer(question, result, *, answerer=None, on_token=None)`
(`compendium/answer/compose.py`) that composes (or refuses) an answer over an already-retrieved
`RetrievalResult` without touching the database — it builds context without a connection or
vault path and returns an `AskResult` with empty `trace_id` / `ask_trace_id`. It is the
composition surface that composition tests and result-holding callers use directly.

#### Scenario: Compose over a covered result without a database

- **GIVEN** a `RetrievalResult` whose coverage is at or above the refusal threshold
- **WHEN** `compose_answer(question, result, answerer=stub)` is called
- **THEN** it returns an `AskResult` with an answer and citations, empty trace ids, and touches no database

#### Scenario: Refuse over a thin result

- **GIVEN** a `RetrievalResult` whose coverage is below the refusal threshold
- **WHEN** `compose_answer(question, result, answerer=stub)` is called
- **THEN** it returns `refused=true`, a null answer, a populated `gap`, and suggested actions — no composition call

### Requirement: `ask` is single-path with no test-only parameter

`compose.ask()` SHALL NOT expose a `_retrieve` (or other test-only) parameter. `ask` SHALL
always retrieve via `pipeline.run`, persist a `query_traces` row and an `ask_traces` row joined
to it, and compose — one production path. Its answer, citations, refusal behaviour, and
persistence SHALL be unchanged from before this change.

#### Scenario: ask persists both traces on a covered question

- **WHEN** `compendium ask` is run for a covered question
- **THEN** a `query_traces` row and a joined `ask_traces` row are written and the returned `AskResult` carries their ids — exactly as before

#### Scenario: no test-only seam remains

- **WHEN** the codebase is searched for `_retrieve`
- **THEN** there are no occurrences in `compendium/` or `tests/` — composition tests cross `compose_answer`, the same function `ask` composes through
