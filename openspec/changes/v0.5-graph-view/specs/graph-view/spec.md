# Spec — v0.5: graph / galaxy visualization in the WebUI (ADR-021)

## ADDED Requirements

### Requirement: A read-only graph export exists
The system SHALL provide a read-only function that returns nodes and typed
edges for a requested scope (a page neighbourhood by default; the full graph as
an option) from Memgraph, bounded by a node/edge limit so large graphs remain
renderable. It SHALL NOT mutate the graph.

#### Scenario: neighbourhood export
- **WHEN** the export is called for a page with a depth/limit
- **THEN** it returns that page's neighbouring nodes and edges within the limit,
  and the graph is unchanged

#### Scenario: bounded full-graph export
- **WHEN** the full-graph export is called on a large graph
- **THEN** it returns at most the node cap (sampled/limited), not an unbounded
  dump

### Requirement: The WebUI renders an interactive, read-only graph
The WebUI SHALL render a force-directed graph of the export, with filtering by
node kind, edge type, and tag, and SHALL open the underlying page when a node is
selected. The view SHALL be read-only (no create/edit/delete), consistent with
the WebUI safe-only posture (ADR-020).

#### Scenario: render + filter
- **WHEN** a user opens the graph view and filters to concept nodes and
  RELATED_TO edges
- **THEN** only those nodes/edges render

#### Scenario: node click opens the page
- **WHEN** a user clicks a node
- **THEN** the corresponding page opens in the WebUI

#### Scenario: read-only
- **WHEN** the graph view is used
- **THEN** no graph or page mutation is possible from it
