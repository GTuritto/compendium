# Spec — the web UI (ADR-015)

## ADDED Requirements

### Requirement: Loopback-only launch via the CLI
`compendium web` SHALL launch Streamlit bound to `127.0.0.1:8501` by default;
the bind address is centralized in the subcommand, and no unit/install verb
exists for it in v0.3.

#### Scenario: default bind
- **WHEN** `compendium web` starts
- **THEN** Streamlit listens on 127.0.0.1 only

### Requirement: A front-end over existing seams only
The app SHALL call `compendium/api/facade.py` for ask/search/pages and the
`tui/data.py` provider (+ Phase 1 resolve) for curation; it adds no
retrieval, answer, compose, or curation logic of its own.

#### Scenario: curation verdicts
- **WHEN** Approve is clicked on a contradiction candidate
- **THEN** the Phase 1 resolve action runs (curator CONTRADICTS edge; signal
  addressed) — the same code path as the CLI and TUI
