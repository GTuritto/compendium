# Spec — v0.6: interactive 3D knowledge-galaxy in the WebUI (ADR-023)

## ADDED Requirements

### Requirement: A read-only semantic-similarity graph export exists
The system SHALL provide a read-only function that returns nodes and
similarity-weighted edges for a requested scope (a page neighbourhood by
default; a bounded full graph as an option), built from Qdrant
nearest-neighbours. Edges SHALL be undirected and carry a similarity weight;
only pairs whose similarity is at or above a configurable threshold SHALL be
emitted. The export SHALL be bounded by a node cap and SHALL NOT mutate any
store.

#### Scenario: neighbourhood export
- **WHEN** the export is called for a page with a top-K and threshold
- **THEN** it returns that page's nearest-neighbour nodes and similarity-weighted
  edges within the node cap, and no store is mutated

#### Scenario: threshold filters weak edges
- **WHEN** a similarity threshold is supplied
- **THEN** only neighbour pairs at or above the threshold appear as edges

#### Scenario: bounded full-graph export
- **WHEN** the full-graph export is called on a large corpus
- **THEN** it returns at most the node cap (sampled/limited), not an unbounded
  dump

### Requirement: The WebUI renders an interactive, read-only 3D galaxy
The WebUI SHALL render an interactive 3D force-directed graph of the export
using a vendored renderer (no pip dependency, no runtime CDN), with nodes
coloured by kind, sized by degree, and edges weighted by similarity, and with
controls for the similarity threshold, top-K, node cap, and node kind. The view
SHALL be read-only (no create/edit/delete), consistent with the WebUI safe-only
posture (ADR-020). The existing graphviz render SHALL remain available as a
no-JS fallback.

#### Scenario: galaxy render
- **WHEN** a user selects the galaxy mode in the Graph view
- **THEN** an interactive 3D graph renders (orbit/zoom/drag), nodes coloured by
  kind and edges weighted by similarity

#### Scenario: threshold control narrows the cloud
- **WHEN** a user raises the similarity threshold
- **THEN** fewer, stronger edges render

#### Scenario: read-only
- **WHEN** the galaxy view is used
- **THEN** no graph, page, or store mutation is possible from it

### Requirement: The renderer is pure and offline-capable
The payload-and-HTML builder SHALL be a pure function (no I/O, no Streamlit) so
it is hermetically testable, and the renderer asset SHALL be vendored so the
loopback WebUI works without network access.

#### Scenario: hermetic builder
- **WHEN** the builder is given a `{nodes, links}` payload
- **THEN** it returns the embeddable HTML deterministically, touching no store
  and no network
