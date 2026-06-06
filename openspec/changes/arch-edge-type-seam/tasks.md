# Tasks — arch-edge-type-seam

Behaviour-preserving consolidation of the semantic-edge rules into one `EdgeType` value object and all semantic-edge writes through one provenance-enforcing seam. No schema migration; no new dependency; no CLI change. One commit per sub-phase, green at HEAD. Boxes unchecked until implementation is approved.

## 1. The `EdgeType` value object + registry (sub-phase a)

- [x] 1.1 `compendium/graph/edge_type.py`: frozen `EdgeType` dataclass (`name`, `automatic`, `symmetric`, `walkable`, `extractable`, `curator_settable`) and the registry of the seven instances with the values from design.md (matching today's behaviour exactly).
- [x] 1.2 Derived tuples computed from the registry: `EDGE_TYPES`, `SEMANTIC_EDGES`, `AUTOMATIC_EDGES`, `EXTRACTABLE_EDGES`, `WALKABLE_EDGES`, `CURATOR_SETTABLE_EDGES`; plus a `by_name` lookup and a `walkable_rel_pattern()` helper returning the `A|B|C` Cypher string.
- [x] 1.3 `tests/test_edge_type.py`: assert each derived tuple equals the known-good set (extractable = RELATED_TO/PREREQUISITE_FOR; walkable = +SYNTHESIZES; symmetric = RELATED_TO only; automatic = the three structural); assert the registry covers exactly the seven types.

## 2. `schema.py` derives tuples + the provenance seam (sub-phase b)

- [x] 2.1 `compendium/graph/schema.py`: reassign `EDGE_TYPES` / `SEMANTIC_EDGES` / `AUTOMATIC_EDGES` / `EXTRACTABLE_EDGES` to the values from `edge_type.py` (names preserved for existing imports; no cycle — `edge_type.py` imports nothing from `schema.py`).
- [x] 2.2 `schema.upsert_semantic_edge(driver, edge_type, from_label, from_id, to_label, to_id, *, provenance) -> "written"|"refreshed"|"collision"`: canonicalise when `EdgeType.symmetric`; protect any existing `extracted_by != "llm"` edge (both directions for symmetric); stamp `provenance`. (Lift the logic out of the current `upsert_extracted_edge`.)
- [x] 2.3 `schema.upsert_extracted_edge` becomes a thin wrapper: `upsert_semantic_edge(..., provenance={extracted_by:"llm", **props})`; signature + return values unchanged so the extractor and its tests are untouched.
- [x] 2.4 Tests: `upsert_semantic_edge` writes/refreshes/collides correctly; a curator (`extracted_by="curator"`) edge survives an LLM re-extraction of the same pair in either orientation; existing `test_extract.py` provenance/collision tests still pass.

## 3. Route the consumers through the object/seam (sub-phase c)

- [x] 3.1 `compendium/graph/links.py`: route the curator write through `upsert_semantic_edge(..., provenance={extracted_by:"curator", weight})` (curator orientation preserved — canonicalisation is LLM-only); `SEMANTIC_EDGES` alias still resolves; `link()` API unchanged.
- [x] 3.2 `compendium/curate/lifecycle.py`: route the `SYNTHESIZES` write through `upsert_semantic_edge(..., provenance={extracted_by:"curator", weight})`.
- [x] 3.3 `compendium/graph/browse.py`: `_SEMANTIC_RELS` derived from `edge_type.walkable_rel_pattern()` (still `RELATED_TO|PREREQUISITE_FOR|SYNTHESIZES`).
- [x] 3.4 `compendium/curate/extract.py`: `_ACTIONABLE` → `EXTRACTABLE_EDGES` (drop the duplicate literal).
- [x] 3.5 `compendium/__main__.py`: `graph link --type` `choices` from `CURATOR_SETTABLE_EDGES` (still the four semantic types).
- [x] 3.6 Tests for the migrated sites: `graph link` still accepts the four types and rejects others; expansion walks the same set; extraction filters to the extractable set.

## 4. Structural-only guard + close-out (sub-phase d)

- [x] 4.1 `schema.upsert_edge`: guard — raise `ValueError` for a non-`automatic` (semantic) edge type, directing to `upsert_semantic_edge`; structural projection (`graph/projection.py`) unaffected (writes only the three automatic types).
- [x] 4.2 Grep gate (a test or smoke note): no semantic edge type is written via `upsert_edge`; the extractable/walkable/curator sets exist as exactly one literal source (the registry).
- [x] 4.3 `docs/Compendium.md`: a one-line note under ADR-009/010 that the per-type rules + provenance enforcement live in `compendium/graph/edge_type.py` + `upsert_semantic_edge`. `CONTEXT.md`: add **edge type** as a first-class value object (distinct from the raw Cypher relationship name).
- [x] 4.4 Append an "Arch fix 2" smoke section to `tests/manual/smoke_test.md`: curator link of a symmetric edge is canonicalised; a curator edge survives `curate run`; expansion still walks the three walkable types; `graph link --type CONTRADICTS` still accepted (curator-only, not walked/extracted).
- [x] 4.5 **Acceptance:** the five literals/strings derive from one registry; every semantic write crosses `upsert_semantic_edge`; `upsert_edge` rejects semantic types; `SYNTHESIZES` carries provenance; curator edges keep their orientation (canonicalisation LLM-only) so directed expansion still reaches them, and are still collision-protected both directions; fast-loop expansion + the extractor behave identically; `tests/test_edge_type.py` plus the existing graph/extract/curate suites green; fast tier and golden green.
- [x] 4.6 `openspec validate arch-edge-type-seam` clean.
