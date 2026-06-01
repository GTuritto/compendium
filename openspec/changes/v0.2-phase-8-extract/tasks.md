# Tasks — v0.2-phase-8-extract

Implements v0.2 Phase 8 of `docs/COMPENDIUM_V0.2_BUILD.md` (ships ADR-010). No schema migration; no new runtime dependency. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. Extraction primitives — graph + kNN (8a)

- [ ] 1.1 `compendium/graph/schema.py` (or `browse.py`): `structural_pairs(driver, label, node_id) -> set[node_key]` — the set of nodes already connected to a node by `PART_OF` / `EVIDENCES` / `GROUNDS` (either direction), for the collision pre-filter.
- [ ] 1.2 `compendium/graph/schema.py`: `upsert_extracted_edge(driver, edge_type, a_label, a_id, b_label, b_id, props)` — `MERGE` the relationship; if it exists with `extracted_by="curator"` leave it untouched and report `collision`; else set the full LLM provenance property set (create or refresh) and report `written`/`refreshed`.
- [ ] 1.3 `compendium/graph/schema.py`: `max_llm_extracted_at(driver) -> datetime | None` — the change-detection watermark (max `extracted_at` over `extracted_by="llm"` edges); `None` when there are none.
- [ ] 1.4 A node-resolution helper shared with `links.py` (source → `:Source`/`source_id`; concept/topic → `:Concept`/`:Topic`/page id) — extract the `_LABEL` map + id rule into a shared function.
- [ ] 1.5 `compendium/curate/extract.py`: `nearest_neighbours(qclient, page_entity_id, k) -> list[neighbour]` over the Qdrant `pages` collection (fetch the page's vector, query top `k+1`, drop self), returning each neighbour's `entity_id` + payload (slug, kind, title).
- [ ] 1.6 Unit tests: `upsert_extracted_edge` creates with provenance, refreshes an existing LLM edge, and leaves a curator edge untouched; `structural_pairs` returns the projected neighbours; `max_llm_extracted_at` returns the latest / `None`.

## 2. The LLM labeller (8b)

- [ ] 2.1 `compendium/curate/extract.py` (or `extract_llm.py`): an `Extractor` protocol with `label(source, neighbours) -> list[Label]` where `Label = {neighbour_id, label in {RELATED_TO, PREREQUISITE_FOR, NONE}, confidence, direction}`.
- [ ] 2.2 `StubExtractor`: deterministic labels for the hermetic tier (no network).
- [ ] 2.3 `LLMExtractor`: one OpenAI-compatible chat call per source page over the `SYNTHESIS_*` config; the prompt (`extract-v1`) presents the source page + the K numbered neighbours and asks for a JSON array of labels + confidence + direction; parse defensively.
- [ ] 2.4 `get_extractor()` gated by `COMPENDIUM_SYNTH_STUB` (mirrors `answer.get_answerer`).
- [ ] 2.5 Unit tests: prompt builds with the neighbours numbered; the LLM JSON is parsed into `Label`s; malformed entries are dropped (not raised); `NONE` labels are filtered.

## 3. The `from_extracted_edges` generator + curate wiring (8c)

- [ ] 3.1 `config/settings.yaml` + `compendium/config.py`: a `curation.extract` block — `enabled: true`, `min_confidence: 0.7`, `top_k_neighbours: 10`, `full_sweep_every: 24`.
- [ ] 3.2 `compendium/curate/extract.py`: `from_extracted_edges(conn, driver, qclient, cfg) -> ExtractReport` — determine changed pages (current revision newer than `max_llm_extracted_at`, or all pages on a full sweep), and for each source page: kNN → drop structural collisions → one LLM `label()` call → drop below `min_confidence` and `NONE` → `upsert_extracted_edge` with provenance (`extracted_by="llm"`, `model`, `confidence`, `extracted_at`, `source_revision_id=current revision`, `weight=confidence`). Log every proposal via structlog with its disposition.
- [ ] 3.3 `compendium/curate/run.py`: invoke `from_extracted_edges` after the ADR-009 generators, inside the `graph_connection()` block, skip-graceful when Memgraph/Qdrant is unreachable; fold its counts into `CurateReport` (`extracted_edges: {written, refreshed, dropped_confidence, dropped_collision}`) and the run summary.
- [ ] 3.4 Full-sweep cadence: cold start (no LLM edges) or every `full_sweep_every` runs; otherwise incremental on changed pages only.
- [ ] 3.5 Integration test (seeded corpus + stores + stub extractor): a `curate run` writes `RELATED_TO`/`PREREQUISITE_FOR` edges with `extracted_by="llm"` + provenance; a pre-existing curator edge on a labelled pair is left untouched; a structurally-linked pair is pre-filtered; `graph status` shows the new edge counts; a follow-up query's trace `graph_expansion` reaches a page via a new LLM edge.

## 4. Operational doc + smoke + acceptance close (8d)

- [ ] 4.1 `docs/operations/edge-extraction.md`: how the extractor runs (inside `curate run` / the daemon); the two edge types and why only those; the provenance property set and the reversible-by-predicate audit queries; the confidence threshold + `weight=confidence`; the watermark + full-sweep cadence; the cost model (one call per changed page); the structlog dispositions.
- [ ] 4.2 Append the Phase 8 (v0.2) smoke section to `tests/manual/smoke_test.md`.
- [ ] 4.3 `README.md`: extend the v0.2 status sentence to mention Phase 8 and link the doc.
- [ ] 4.4 `CLAUDE.md`: status sentence catches up to Phase 8; the v0.2 phases bullet gains a Phase 8 entry; the **"Not automated semantic-edge extraction"** exclusion line is updated to point at ADR-010 with the per-type qualifier (`RELATED_TO`/`PREREQUISITE_FOR` autonomous; `SYNTHESIZES` lifecycle-owned; `CONTRADICTS` curator-only).
- [ ] 4.5 `docs/Compendium.md`: ADR-010 status note (shipped, PR number at merge).
- [ ] 4.6 `docs/COMPENDIUM_V0.2_BUILD.md`: Status section gains a Phase 8 merged entry; mark v0.2 feature-complete.
- [ ] 4.7 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 8: the `from_extracted_edges` generator runs inside `curate run`; per changed page (+ full sweep) it pulls K=10 Qdrant neighbours and asks the LLM to label each pair `RELATED_TO`/`PREREQUISITE_FOR`/`NONE` + confidence; edges above 0.7 are written with full provenance; curator edges are never overwritten; LLM edges refresh on re-extraction; structurally-linked pairs are pre-filtered; every proposal is logged; the smoke walk shows new `extracted_by="llm"` edges, an untouched curator edge, updated `graph status` counts, and fast-loop expansion finding the new edges.
- [ ] 4.8 `openspec validate v0.2-phase-8-extract` clean.
