# Spec — contradiction candidates (ADR-014)

## ADDED Requirements

### Requirement: The LLM proposes, never writes
The slow loop SHALL write `contradiction_candidate` curation signals only; no
code path lets the generator write a `CONTRADICTS` edge.

#### Scenario: a candidate is a signal, not an edge
- **WHEN** `curate run` proposes a contradiction
- **THEN** a `contradiction_candidate` signal exists with slugs, confidence,
  and rationale, and `graph status` shows `CONTRADICTS: 0`

### Requirement: Approval is a curator write
`curate resolve <id> --approve` SHALL write the `CONTRADICTS` edge through the
curator path (`extracted_by="curator"`, persisted per ADR-013) and mark the
signal `addressed`; `--drop` SHALL mark it `dropped` and write nothing.

#### Scenario: approve then rebuild
- **WHEN** a candidate is approved and `graph rebuild` runs
- **THEN** the `CONTRADICTS` edge survives (replayed from PostgreSQL)

### Requirement: No re-proposal
A pair already linked by any edge, or already carrying a
`contradiction_candidate` signal in any status, SHALL be pre-filtered before
the LLM is asked.

#### Scenario: approved pair is quiet
- **WHEN** `curate run` runs again after an approval
- **THEN** no new candidate for that pair is proposed
