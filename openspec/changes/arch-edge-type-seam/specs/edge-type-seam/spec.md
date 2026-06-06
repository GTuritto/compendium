## ADDED Requirements

### Requirement: A single `EdgeType` value object is the source of per-type edge rules

The system SHALL provide an `EdgeType` value object (`compendium/graph/edge_type.py`) carrying, per edge type, whether it is `automatic` (structural), `symmetric`, `walkable` (traversed by fast-loop expansion), `extractable` (the LLM may write it), and `curator_settable`. Derived tuples (`SEMANTIC_EDGES`, `AUTOMATIC_EDGES`, `EXTRACTABLE_EDGES`, `WALKABLE_EDGES`, `CURATOR_SETTABLE_EDGES`, `EDGE_TYPES`) SHALL be computed from the registry, not declared independently. The previously scattered literals SHALL consult this object.

#### Scenario: The per-type rules match the established behaviour

- **WHEN** the registry is read
- **THEN** `extractable` is exactly `{RELATED_TO, PREREQUISITE_FOR}`, `walkable` is exactly `{RELATED_TO, PREREQUISITE_FOR, SYNTHESIZES}`, `curator_settable` is the four semantic types, `symmetric` is exactly `{RELATED_TO}`, and `automatic` is exactly `{PART_OF, EVIDENCES, GROUNDS}`

#### Scenario: The consumers derive from the object, not from copies

- **WHEN** `graph/browse.py`, `curate/extract.py`, and the `graph link` CLI choices are evaluated
- **THEN** the walkable relationship set, the extractable label set, and the curator-settable choices all derive from the `EdgeType` registry — no second literal copy of any of these sets exists in the codebase

#### Scenario: Adding or changing one type touches one place

- **WHEN** a type's `walkable` (or `extractable`, etc.) flag is changed in the registry
- **THEN** fast-loop expansion (and the extractor, etc.) reflect the change with no edit to `browse.py` / `extract.py` / `__main__.py`

### Requirement: All semantic-edge writes go through one provenance-enforcing seam

The system SHALL provide `schema.upsert_semantic_edge` and route every semantic-edge writer (curator links, LLM extraction, the SYNTHESIZES lifecycle) through it. The seam SHALL own canonicalisation for symmetric types, the "never overwrite a `extracted_by != "llm"` edge" protection (checked in both directions for symmetric types), and provenance stamping. The generic `schema.upsert_edge` SHALL reject a semantic edge type, directing callers to the seam; it remains the writer for the three structural types only.

#### Scenario: A curator edge is never overwritten by extraction

- **GIVEN** a curator `RELATED_TO` edge between two pages (`extracted_by="curator"`)
- **WHEN** the LLM extractor labels that same pair `RELATED_TO` and writes through the seam
- **THEN** the existing curator edge is left unchanged and the write returns `"collision"` — regardless of which orientation the curator originally used

#### Scenario: Curator symmetric edges are canonicalised

- **WHEN** a curator links `RELATED_TO` from a higher-id page to a lower-id page
- **THEN** the stored edge is canonicalised (one edge per unordered pair), matching the orientation the extractor would use, so the two write paths cannot produce a duplicate pair

#### Scenario: SYNTHESIZES edges carry provenance

- **WHEN** the promote lifecycle adds a `SYNTHESIZES` edge through the seam
- **THEN** the edge carries explicit provenance (`extracted_by="curator"`) and is protected from any LLM overwrite

#### Scenario: The generic upsert rejects semantic types

- **WHEN** `schema.upsert_edge` is called with a semantic edge type
- **THEN** it raises, directing the caller to `upsert_semantic_edge`; called with a structural type (`PART_OF`/`EVIDENCES`/`GROUNDS`) it writes as before

### Requirement: The refactor is behaviour-preserving

The change SHALL preserve ADR-009 (curator-driven semantic edges) and ADR-010 (autonomous `RELATED_TO`/`PREREQUISITE_FOR` extraction with provenance): the walkable set, the extractable set, the curator-protection semantics, the confidence/threshold handling, and the `compendium graph link` CLI surface are unchanged. No Memgraph re-projection or migration is required.

#### Scenario: Fast-loop expansion is unchanged

- **WHEN** a query expands over semantic edges after the refactor
- **THEN** it walks exactly `RELATED_TO` / `PREREQUISITE_FOR` / `SYNTHESIZES` (CONTRADICTS still excluded), as before

#### Scenario: The extractor behaves identically

- **WHEN** `compendium curate run` extracts edges after the refactor
- **THEN** it writes the same `RELATED_TO`/`PREREQUISITE_FOR` edges with the same provenance and threshold behaviour as before, and the existing extraction tests pass unchanged
