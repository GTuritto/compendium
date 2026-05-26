## ADDED Requirements

### Requirement: TUI launch and navigation

The system SHALL provide a `compendium tui` command that launches a Textual ops console. The console SHALL be operable by keyboard alone (no mouse required), expose a global binding to quit and a binding to show help, and let the user reach every screen via a key binding shown in a persistent footer.

#### Scenario: The console launches and shows navigation

- **WHEN** `compendium tui` starts
- **THEN** the app mounts with a default screen and a footer listing the screen and quit/help bindings

#### Scenario: Quit binding exits cleanly

- **WHEN** the quit binding is pressed
- **THEN** the app exits without error

### Requirement: Dashboard screen

The console SHALL provide a dashboard screen showing point-in-time table counts, the sync-lag breakdown from `v_sync_lag`, and recent query traces from `v_recent_traces`, with a binding to refresh.

#### Scenario: Dashboard renders operational state

- **WHEN** the dashboard screen is shown
- **THEN** it displays table counts, the per-index/state sync-lag rows, and recent traces

### Requirement: Source list screen with ingest

The console SHALL provide a source-list screen listing sources with their inspection status (failures distinguished, per `v_failed_sources`), and an ingest action that accepts a path and runs ingestion off the UI thread, refreshing the list on completion.

#### Scenario: Sources are listed with status

- **WHEN** the source-list screen is shown
- **THEN** each source appears with its kind, title, and inspection status

#### Scenario: Ingest from the TUI

- **WHEN** the user invokes the ingest action with a valid path
- **THEN** ingestion runs without freezing the UI and the source list reflects the new source on completion

### Requirement: Page list screen with synth

The console SHALL provide a page-list screen listing wiki pages, filterable by kind and status, and a synth action that accepts a concept/topic name and runs synthesis off the UI thread, refreshing the list on completion.

#### Scenario: Pages are listed and filterable

- **WHEN** the page-list screen is shown and a kind or status filter is applied
- **THEN** only matching pages are listed

#### Scenario: Synth from the TUI

- **WHEN** the user invokes the synth action with a name
- **THEN** synthesis runs without freezing the UI and the new page appears in the list on completion

### Requirement: Query workbench screen

The console SHALL provide a query-workbench screen where the user types a query, runs the retrieval pipeline off the UI thread, and inspects the result: the ranked pages, coverage score, fallback flag, and the persisted trace's stages. The run SHALL persist a query trace.

#### Scenario: Running a query in the workbench

- **WHEN** the user enters a query and runs it
- **THEN** the ranked pages, coverage, and fallback are shown and a `query_traces` row is persisted

### Requirement: Curation queue screen

The console SHALL provide a read-only curation-queue screen rendering open signals from `v_open_curation_signals` (kind, priority, summary, created-at). The screen SHALL be reachable and render correctly when the queue is empty. Curator actions on signals are out of scope for this phase.

#### Scenario: Empty queue renders

- **WHEN** the curation-queue screen is shown with no open signals
- **THEN** it renders an empty queue without error

#### Scenario: Open signals are listed

- **WHEN** open signals exist in `v_open_curation_signals`
- **THEN** they are listed by priority with their kind and created-at

### Requirement: Graph browser screen

The console SHALL provide a graph-browser screen that searches Memgraph nodes (by title or slug) and walks typed edges up to N hops from a selected node, rendering the reachable nodes and the edges traversed.

#### Scenario: Searching and walking the graph

- **WHEN** the user searches for a node and walks its edges N hops
- **THEN** the reachable nodes and the typed edges between them are shown

#### Scenario: Graph unreachable is handled

- **WHEN** Memgraph is not reachable
- **THEN** the graph-browser screen reports it rather than crashing the app

### Requirement: Responsive UI under blocking work

All database reads, graph queries, ingestion, synthesis, and retrieval triggered from the TUI SHALL run off the UI thread (Textual `@work(thread=True)`), so the interface remains responsive while work is in progress, and a worker failure SHALL surface as an error in the screen rather than crashing the app.

#### Scenario: A long operation does not freeze the UI

- **WHEN** a screen triggers a blocking operation (ingest, synth, query, or a data load)
- **THEN** the app remains responsive and shows the result or an error when the worker completes
