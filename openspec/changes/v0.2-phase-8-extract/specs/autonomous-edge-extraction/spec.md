## ADDED Requirements

### Requirement: The slow loop autonomously extracts `RELATED_TO` and `PREREQUISITE_FOR` edges

The system SHALL provide a `from_extracted_edges` generator in `compendium/curate/` that runs inside `compendium curate run` (and therefore the scheduled daemon). For each source page in scope, it SHALL pull the top `curation.extract.top_k_neighbours` (default 10) nearest neighbours from the Qdrant `pages` collection and ask the LLM, in **one prompt per source page**, to label each pair as `RELATED_TO`, `PREREQUISITE_FOR`, or `NONE` with a confidence. Labels above `curation.extract.min_confidence` (default `0.7`) and not `NONE` SHALL be written to Memgraph. `SYNTHESIZES` and `CONTRADICTS` SHALL NOT be autonomously extracted. The generator SHALL skip gracefully when Memgraph or Qdrant is unreachable, like the other graph-backed generators.

#### Scenario: A run writes extracted edges for a changed page

- **GIVEN** a seeded corpus, Memgraph + Qdrant up, and a page changed since the last extraction
- **WHEN** `compendium curate run` executes
- **THEN** the LLM is asked once for that page's K neighbours, and each above-threshold non-`NONE` label is written as a `RELATED_TO` or `PREREQUISITE_FOR` edge in Memgraph

#### Scenario: Only the two permitted edge types are extracted

- **WHEN** the extractor writes edges
- **THEN** it writes only `RELATED_TO` and `PREREQUISITE_FOR`; it never writes `SYNTHESIZES` (lifecycle-owned) or `CONTRADICTS` (curator-only)

#### Scenario: One LLM call per source page

- **WHEN** a source page with K candidate neighbours is processed
- **THEN** exactly one LLM call is made for that page (not one per pair)

### Requirement: Extracted edges carry full provenance and never overwrite curator edges

Each extracted edge SHALL carry the relationship properties `extracted_by="llm"`, `model`, `confidence`, `extracted_at`, `source_revision_id` (the page revision that triggered the extraction), and `weight`. An existing edge with `extracted_by="curator"` SHALL NOT be overwritten. An existing edge with `extracted_by="llm"` SHALL have its provenance refreshed on re-extraction.

#### Scenario: A curator edge on a labelled pair is left untouched

- **GIVEN** a curator-added `RELATED_TO` edge between two pages (`extracted_by="curator"`)
- **WHEN** the extractor would label that same pair `RELATED_TO`
- **THEN** the existing curator edge is left unchanged and the proposal is logged as `dropped-by-collision`

#### Scenario: An LLM edge refreshes on re-extraction

- **GIVEN** an existing `extracted_by="llm"` edge between two pages
- **WHEN** the extractor re-labels that pair above threshold
- **THEN** the edge's `confidence`, `extracted_at`, `source_revision_id`, and `weight` are refreshed (no duplicate edge is created)

#### Scenario: Provenance makes the decision reversible by predicate

- **WHEN** the curator runs `MATCH ()-[r {extracted_by:"llm"}]-() WHERE r.confidence < 0.85 DELETE r`
- **THEN** only low-confidence LLM edges are removed; curator edges are unaffected

### Requirement: Structural-collision pre-filter and confidence threshold

Before the LLM call, candidate pairs already connected by a structural edge (`PART_OF` / `EVIDENCES` / `GROUNDS`, either direction) SHALL be removed from the candidate set. After labelling, proposals below `curation.extract.min_confidence` SHALL be dropped. Every proposal SHALL be logged via structlog with a disposition of `accepted`, `dropped-by-confidence`, `dropped-by-collision`, or `written`.

#### Scenario: A structurally-linked pair is pre-filtered

- **GIVEN** two pages already connected by a `GROUNDS` edge
- **WHEN** that page appears among a source page's neighbours
- **THEN** the pair is removed before the LLM call (no label requested for it)

#### Scenario: A low-confidence label is dropped

- **GIVEN** the LLM labels a pair `RELATED_TO` with confidence `0.5` and the threshold is `0.7`
- **WHEN** the extractor processes the label
- **THEN** no edge is written and the proposal is logged `dropped-by-confidence`

### Requirement: Change detection processes changed pages with a periodic full sweep

The extractor SHALL process pages whose current revision is newer than the change-detection watermark (the maximum `extracted_at` over `extracted_by="llm"` edges in Memgraph), plus a periodic full sweep. A full sweep SHALL run when there are no LLM edges yet (cold start) or every `curation.extract.full_sweep_every` runs. No PostgreSQL schema migration is required for change detection.

#### Scenario: Cold start runs a full sweep

- **GIVEN** no `extracted_by="llm"` edges exist
- **WHEN** `compendium curate run` executes
- **THEN** the extractor processes all in-scope pages (a full sweep)

#### Scenario: Incremental run processes only changed pages

- **GIVEN** LLM edges exist and one page has a revision newer than the watermark
- **WHEN** a (non-full-sweep) `compendium curate run` executes
- **THEN** only that changed page is processed

### Requirement: Operational document and smoke section

The repository SHALL include `docs/operations/edge-extraction.md` covering: how the extractor runs (inside `curate run` / the daemon); the two extracted edge types and why only those; the provenance property set and the reversible-by-predicate audit queries; the confidence threshold and `weight=confidence`; the watermark and full-sweep cadence; the one-call-per-changed-page cost model; the structlog dispositions. `tests/manual/smoke_test.md` SHALL include a Phase 8 (v0.2) section: run the slow loop on a seeded corpus, observe new `RELATED_TO`/`PREREQUISITE_FOR` edges with `extracted_by="llm"`, observe a curator-added edge staying untouched, observe `compendium graph status` showing the new counts, and observe the fast-loop expansion finding the new edges.

#### Scenario: The operational doc covers the required sections

- **WHEN** the curator reads `docs/operations/edge-extraction.md` after Phase 8 merges
- **THEN** it explains the run context, the two edge types, the provenance + audit queries, the threshold, the watermark + full-sweep cadence, the cost model, and the structlog dispositions

#### Scenario: The smoke walk exercises extraction end-to-end

- **WHEN** the operator walks the Phase 8 (v0.2) smoke section
- **THEN** a slow-loop run produces `extracted_by="llm"` edges, a curator edge is untouched, `graph status` shows the new counts, and a query's trace `graph_expansion` reaches a page via a new LLM edge
