# Spec — v0.5: tagging (ADR-019)

## ADDED Requirements

### Requirement: Tags are curator-assigned labels on sources and pages
The system SHALL persist free-form tags in PostgreSQL and attach them to
sources and wiki pages. Tags SHALL be distinct from topics (ADR-006) and
aliases; assigning or removing a tag SHALL NOT create a topic, an alias, or a
graph edge.

#### Scenario: tag a source and a page
- **WHEN** the curator tags a source and a concept page with `trading`
- **THEN** both carry the tag, queryable from PostgreSQL, with no topic/alias/
  edge side effects

#### Scenario: remove a tag
- **WHEN** a tag is removed from a page
- **THEN** the attachment is gone and the tag definition persists if still used
  elsewhere

### Requirement: Tags scope retrieval
The retrieval pipeline SHALL accept an optional tag filter; with a filter set,
results SHALL be restricted to pages/chunks whose source or page carries a
matching tag. The applied filter SHALL be recorded in the query trace.

#### Scenario: filtered query
- **WHEN** `query "<q>" --tag trading` runs
- **THEN** only results tagged `trading` (directly or via their source) are
  returned, and the trace records the filter

#### Scenario: unfiltered query is unchanged
- **WHEN** a query runs with no tag filter
- **THEN** behaviour is identical to pre-tagging (the fast tier is green)

### Requirement: Tags are filterable in the derived indexes
On `reindex` / sync, tags SHALL be written into the OpenSearch and Qdrant
payloads as a filterable field so the filter is enforced at the index, not
post-hoc.

#### Scenario: reindex carries tags
- **WHEN** a tagged source is reindexed
- **THEN** its index documents/points carry the tag field and the index-level
  filter returns them

### Requirement: Assign and filter from every surface
Tagging and tag-filtering SHALL be available on the CLI, the TUI, and the
WebUI. The WebUI surface is non-destructive and therefore permitted (ADR-020).

#### Scenario: surfaces
- **WHEN** a curator uses the CLI, TUI, or WebUI
- **THEN** each can add/remove tags and filter by tag
