## ADDED Requirements

### Requirement: A `SignalGenerator` registry is the home for the slow loop's generators

The system SHALL provide a `SignalGenerator` registry (`compendium/curate/signal_generator.py`) carrying, per generator, its `name`, the signal `kinds` it can emit, the stores it `requires` (a subset of `{"postgres", "graph"}`), and a `generate(ctx) -> list[Signal]` callable. A `GenerationContext` value object SHALL carry the stores (`conn`, `driver`) and tuned thresholds the generators read. `Signal` SHALL be a named record that still unpacks as `(kind, priority, payload)`. `compendium curate run` SHALL iterate the registry rather than hardwiring the generator calls or restating the signal kinds as a literal.

#### Scenario: One registry entry per signal generator

- **WHEN** the registry is read
- **THEN** it has one record per signal generator (low-coverage, thin-grounding, dangling, contradictions), each declaring its `kinds` and `requires`, and `curate run` no longer contains a hardcoded list of graph signal kinds

#### Scenario: A new generator is one registry entry

- **WHEN** a new signal generator is added to the registry with its `kinds` and `requires`
- **THEN** `curate run` picks it up with no edit to the run loop — it is invoked when its required stores are reachable and its kinds are recorded in `skipped` when they are not

### Requirement: Store-reachability skip derives from each generator's declaration

The runner SHALL skip a generator (recording that generator's `kinds` in the run's `skipped` list) when any store in its `requires` is unreachable, or when its `generate` raises. The skipped kinds SHALL derive from the generators' `kinds`, not from a hardcoded list.

#### Scenario: Graph down skips exactly the graph generators

- **GIVEN** Memgraph is unreachable and PostgreSQL is up
- **WHEN** `curate run` executes
- **THEN** the low-coverage generator runs, the three graph generators are skipped, and `skipped` contains exactly their kinds (`thin_grounding`, `dangling_concept`, `unresolved_contradiction`)

#### Scenario: One failing graph query no longer suppresses its siblings

- **GIVEN** Memgraph is up but one graph generator's query raises
- **WHEN** `curate run` executes
- **THEN** only that generator's kinds are recorded in `skipped`; the other graph generators still produce their signals

### Requirement: The refactor is behaviour-preserving and the extractor stays separate

`curate run` SHALL produce the same signal kinds, priorities, payloads, dedup behaviour, and `graph_analysis_runs` summary as before. The autonomous edge extractor (`from_extracted_edges`, ADR-010) SHALL remain a separate step that writes edges and returns counts — it is NOT a `SignalGenerator`.

#### Scenario: Same signals on the same corpus

- **GIVEN** a seeded corpus with low-coverage traces and graph gaps
- **WHEN** `curate run` executes after the refactor
- **THEN** it inserts the same signals (kind / priority / payload), dedups against open signals identically, and records the same `by_kind` / `skipped` / `extracted_edges` summary as before

#### Scenario: Extraction is not modelled as a signal generator

- **WHEN** the registry is enumerated
- **THEN** `from_extracted_edges` is absent from it; extraction runs as its own step in `curate run`, writing `RELATED_TO`/`PREREQUISITE_FOR` edges and folding its counts into the report
