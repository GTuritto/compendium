## ADDED Requirements

### Requirement: Query-time graph expansion (fast loop)

After fusing the page results, the retrieval pipeline SHALL walk Memgraph from the top seed pages over the semantic edges (`RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`) up to a configured hop limit, scoring each reached page with a decayed weight and merging it into the ranked list, and SHALL record the expansion in `query_traces.graph_expansion`. Expansion SHALL be gated by config and by Memgraph reachability: when disabled, when no semantic edges exist, or when Memgraph is unreachable, it SHALL be a no-op and `graph_expansion` SHALL remain null, leaving the base ranking unchanged.

#### Scenario: Expansion surfaces a related page

- **WHEN** a query runs and a top result has a semantic edge to another page
- **THEN** the connected page is merged into the ranked list with a decayed expansion score and `query_traces.graph_expansion` records the seeds, reached pages, and edges

#### Scenario: No semantic edges is a no-op

- **WHEN** a query runs and no semantic edges exist (or Memgraph is unreachable)
- **THEN** the ranked list is unchanged from the base fusion and `graph_expansion` is null

### Requirement: Slow-loop signal generation

`compendium curate run` SHALL perform one analysis pass that records a `graph_analysis_runs` row and writes prioritized `graph_curation_signals` for: low-coverage / fallback queries (`low_coverage_query`, `gap`), concepts with fewer than the configured minimum `GROUNDS` edges (`thin_grounding`), concepts with no `PART_OF` edge to a topic (`dangling_concept`), and unresolved `CONTRADICTS` edges (`unresolved_contradiction`). It SHALL NOT create a duplicate open signal for a condition that already has one, and SHALL complete the run with a signal count and summary.

#### Scenario: A low-coverage query produces a signal

- **WHEN** `compendium curate run` runs after a query that fell back to chunks / scored below the coverage threshold
- **THEN** an open `low_coverage_query` (or `gap`) signal is written referencing that query's trace, and a completed `graph_analysis_runs` row records the pass

#### Scenario: Re-running does not duplicate open signals

- **WHEN** `compendium curate run` is invoked twice with no change in the underlying conditions
- **THEN** the second pass adds no duplicate open signal for an already-open condition

#### Scenario: Memgraph-dependent generators degrade gracefully

- **WHEN** `compendium curate run` runs while Memgraph is unreachable
- **THEN** the Postgres-derived signals are still produced and the run summary notes the skipped graph generators, without aborting

### Requirement: Curator signal listing and synth

`compendium curate list` SHALL list open signals by priority. `compendium curate synth <signal-id>` SHALL trigger synthesis derived from the signal's payload, producing a draft wiki page revision and moving the signal to `in_progress`.

#### Scenario: Synthesizing from a signal

- **WHEN** `compendium curate synth <signal-id>` runs for an open signal
- **THEN** a draft page is synthesized from the signal payload, the page lint-passes and cites real chunks, and the signal becomes `in_progress`

### Requirement: Promotion addresses the signal and updates the graph

When a page synthesized from a signal is promoted, the system SHALL mark the originating signal `addressed` with the promoted revision as its `addressed_revision_id`, and SHALL add `SYNTHESIZES` edges from the new page to the inputs it drew from.

#### Scenario: Promoting a synth'd page closes the signal and improves replay

- **WHEN** the page synthesized from a signal is promoted
- **THEN** the signal's status becomes `addressed` with the promoted revision recorded, `SYNTHESIZES` edges are added, and a replay of the originating query reflects the new page (higher coverage or the new page in the ranking)

### Requirement: Curator-driven semantic edges

`compendium graph link <from> <to> --type {RELATED_TO,PREREQUISITE_FOR,SYNTHESIZES,CONTRADICTS}` SHALL create a single typed semantic edge between two existing pages, validating that both endpoints exist and that the type is one of the four semantic kinds. Automated semantic-edge extraction SHALL NOT be performed in this phase.

#### Scenario: Adding a semantic edge by hand

- **WHEN** `compendium graph link a-slug b-slug --type RELATED_TO` runs for two existing pages
- **THEN** a `RELATED_TO` edge from page a to page b exists in Memgraph

#### Scenario: Rejecting an unknown endpoint or non-semantic type

- **WHEN** the command is given a slug that does not resolve, or an automatic edge type (e.g. `PART_OF`)
- **THEN** it reports the error and creates no edge

### Requirement: TUI curation actions

The Phase 8 curation-queue screen SHALL let the curator select an open signal and trigger its synth off the UI thread, and SHALL reflect the signal's status transitions (`open` → `in_progress` → `addressed`).

#### Scenario: Triggering a synth from the curation screen

- **WHEN** the curator selects an open signal in the TUI and triggers its synth
- **THEN** synthesis runs in a worker and the signal's status updates in the list when it completes
