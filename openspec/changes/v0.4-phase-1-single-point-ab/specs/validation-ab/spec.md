# Spec — v0.4 Phase 1: the single-point A/B (ADR-016)

## ADDED Requirements

### Requirement: A chunk-only control arm exists and is fenced
The retrieval pipeline SHALL accept `arm="chunks"`, running the existing
BM25 + dense chunk fan-out and RRF fusion unconditionally and returning
ranked chunks, with the arm recorded in the persisted trace. The arm SHALL
be reachable only via the `validate` verbs — `compendium query` and the
facade never expose it.

#### Scenario: control arm returns ranked chunks with a trace
- **WHEN** the pipeline runs with `arm="chunks"` against the fixture corpus
- **THEN** ranked chunks are returned, no page ranking is produced, and the
  trace records the arm

#### Scenario: the supported surfaces are unchanged
- **WHEN** `compendium query` or any facade verb runs
- **THEN** behaviour is byte-identical to pre-Phase-1 (wire-format snapshots
  from Phase 0 still pass; the full fast tier is green)

### Requirement: The probe set is real, frozen, and outside the repo
`compendium validate harvest` SHALL list distinct `ask_traces` questions for
curation into a slug-keyed YAML probe set whose default location is
`~/.compendium/probes/`; the repo and the 2Deploy bundle SHALL NOT contain
real probe queries (the test suite uses a canned fixture probe set).

#### Scenario: harvest from ask traces
- **WHEN** `validate harvest` runs against a database with ask traces
- **THEN** it emits candidate probes (query text + trace metadata) for the
  curator to curate and freeze; nothing is written into the repository

### Requirement: The A/B run is deterministic and page-scored
`compendium validate run --probes <file>` SHALL run every probe through both
arms with Qdrant exact search on both, score both arms in page space (a
chunk credits its parent source page), and emit a per-query comparison
(text table + JSON artifact) of page-arm versus chunk-arm metrics.

#### Scenario: per-query delta on identical data
- **WHEN** `validate run` executes over the fixture probe set
- **THEN** each probe yields metrics for both arms and their delta, computed
  on the same corpus state in the same process

#### Scenario: determinism
- **WHEN** `validate run` executes twice with no ingest between
- **THEN** the two reports are identical (exact search removes the HNSW flap)

### Requirement: Measurement decisions are pre-registered
The report SHALL record in its output the three pre-registered decisions —
page-space scoring, normalization applied to both arms, exact search — so a
reader of any saved report knows the methodology it was produced under.

#### Scenario: methodology header
- **WHEN** any report is generated
- **THEN** it carries the methodology block with those three decisions
