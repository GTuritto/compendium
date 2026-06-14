# Spec — v0.5: hard delete of sources (ADR-018)

## ADDED Requirements

### Requirement: A source and all its derivatives are hard-deleted
`delete_source` SHALL remove a source and everything derived from it: the
`sources` row and its cascaded `source_documents` and `chunks`, the source
`wiki_pages` row and its vault markdown file, the `semantic_edges` rows
referencing the source or its chunks, the OpenSearch documents and Qdrant
points for the page and chunks, the Memgraph Source/Chunk nodes and their
edges, and the related `index_sync_state` rows. After deletion the source is
absent from every store and from retrieval.

#### Scenario: full purge
- **WHEN** `delete_source` runs for an ingested source
- **THEN** no rows, vault file, index entries, or graph nodes for that source
  remain, and a query that previously surfaced it no longer returns it

#### Scenario: re-ingest after delete is clean
- **WHEN** the same file is ingested again after a hard delete
- **THEN** it ingests as a fresh source (no tombstone, no resurrection of the
  old identity)

### Requirement: Deletion is canonical-first and self-reconciling
`delete_source` SHALL remove the canonical record (PostgreSQL rows + vault
file) before the derived-index entries. A failure to delete from a derived
index SHALL NOT leave the canonical record present, and a subsequent `reindex`
+ `graph rebuild` SHALL reconcile any derived entry the orchestration missed.

#### Scenario: partial derived failure heals
- **WHEN** a derived-index delete fails mid-orchestration after the canonical
  rows are gone
- **THEN** the source is still absent from the canonical layer, and `reindex`
  + `graph rebuild` bring the derived stores into agreement

### Requirement: Grounded concepts are surfaced, not cascade-deleted
Hard-deleting a source SHALL NOT delete concept pages that were grounded on
it. A concept left thinly grounded or dangling SHALL be detectable by the slow
loop (ADR-009) as a curation signal.

#### Scenario: dangling concept becomes a signal
- **WHEN** a source that solely grounded a concept is deleted
- **THEN** the concept page still exists and the next `curate run` surfaces it
  as a thin-grounding / dangling-concept signal

### Requirement: Delete is destructive and stays off the network surface
The delete capability SHALL be exposed only via the CLI (`compendium source
delete`) and the TUI. It SHALL NOT be added to the facade, HTTP, or MCP
access surface.

#### Scenario: surfaces
- **WHEN** the access surface (HTTP/MCP) is inspected
- **THEN** no delete verb is present; delete exists only on the CLI and TUI

### Requirement: Dry-run and confirmation
`compendium source delete` SHALL support `--dry-run`, reporting what would be
removed (chunk/page/index counts and any concepts that would be left thinly
grounded) without removing anything. The TUI action SHALL require an explicit
confirmation. `--force` SHALL override the refusal-on-sole-grounding guard if
that guard is adopted.

#### Scenario: dry-run removes nothing
- **WHEN** `source delete --dry-run` runs
- **THEN** it prints the impact summary and the corpus is unchanged
