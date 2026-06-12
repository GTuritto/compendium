# Spec — v0.4 Phase 0: clear the deck

## ADDED Requirements

### Requirement: The access-surface wire format is byte-frozen
For each facade verb payload shape (`query`, `ask`, `ingest`, `page_get`,
`page_list`, `index_status`), a snapshot test SHALL assert that
`render.to_json` over a canned input equals a frozen literal byte-for-byte,
so any change to the wire format is a deliberate test edit, not an accident.

#### Scenario: a rendering change breaks the snapshot
- **WHEN** a field is renamed, reordered, or reformatted anywhere on a facade
  payload path
- **THEN** the corresponding snapshot test fails, naming the wire contract in
  its assertion message

#### Scenario: serializer equivalence is preserved
- **WHEN** the snapshots pass
- **THEN** `api/serialize.to_payload` of the same canned inputs parses to the
  identical structure (the existing equivalence test keeps holding)

### Requirement: Unknown models are loud, not zero-and-silent
`estimate_cost` SHALL log one structlog warning (`unknown_model_rate`,
carrying the model name) when asked to price a model absent from the rate
table, excluding the stub. The returned estimate stays `0.0` and the
`ask_traces.cost_estimate` column shape is unchanged.

#### Scenario: unknown model
- **WHEN** `ask` runs with `SYNTHESIS_MODEL` set to a model not in `_RATES`
- **THEN** a warning is logged and `cost_estimate` records 0.0

#### Scenario: known model
- **WHEN** the model is in `_RATES`
- **THEN** no warning is logged and the estimate uses the table rates

### Requirement: The mutmut experiment is retired on record
The `mutants/` tree SHALL be deleted locally and draft PR #47 closed with a
comment citing the v0.4 Phase 0 verdict, so the experiment stops taxing
future explorers and review #6 does not re-suggest adopting it.

#### Scenario: post-phase state
- **WHEN** Phase 0 completes
- **THEN** `mutants/` does not exist on disk, `.gitignore` still carries the
  pattern, and PR #47 is closed (not merged)
