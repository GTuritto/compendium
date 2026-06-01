## Why

ADR-009 made all four semantic edge types curator-driven in v0.1: every `RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, and `CONTRADICTS` edge is approved by a human (via `compendium graph link` or, for `SYNTHESIZES`, the promote hook). That preserves trust but leaves the graph thin — most genuinely-related page pairs never get an edge because the curator never has time — so the fast-loop graph expansion (ADR-009) under-fires. v0.2's thesis includes "an LLM-densified graph"; Phase 8 is the v0.2 phase that **ships ADR-010** and reverses, selectively, the v0.1 exclusion line *"Not automated semantic-edge extraction."*

The autonomy is deliberately narrow and reversible:

1. **Two edge types only.** The slow loop autonomously writes `RELATED_TO` and `PREREQUISITE_FOR`. `SYNTHESIZES` stays owned by `curate/lifecycle.address_on_promote` (the promote hook) and `CONTRADICTS` stays curator-only via `graph link` (deferred to v0.3+). This keeps the strongest claims human-gated.
2. **Provenance on every extracted edge.** Each LLM edge carries `extracted_by="llm"`, `model`, `confidence`, `extracted_at`, `source_revision_id`, and `weight` as relationship properties — so the decision is reversible by a Cypher predicate (`MATCH ()-[r {extracted_by:"llm"}]-() WHERE r.confidence < 0.85 DELETE r`) and auditable any time. Curator-added edges (`extracted_by="curator"`) are never overwritten.
3. **Bounded cost.** The extractor runs inside `compendium curate run` (and therefore the scheduled daemon). Per run, for each page changed since the last extraction (with a periodic full sweep), it pulls the top **K=10 nearest neighbours from Qdrant** and asks the LLM, in **one prompt per source page**, to label each pair `RELATED_TO`, `PREREQUISITE_FOR`, or `NONE` with a confidence. Cost scales with corpus turnover, not corpus size.

## What Changes

- **A fifth signal/work generator** `from_extracted_edges` in `compendium/curate/` (a new `compendium/curate/extract.py`), invoked by `compendium curate run` after the four ADR-009 generators. It is graph-backed (skips gracefully when Memgraph or Qdrant is unreachable, like the existing graph generators).
- **Change detection.** The extractor processes pages whose current revision is newer than the last extraction watermark, plus a periodic full sweep. The watermark is derived from the graph (the max `extracted_at` over `extracted_by="llm"` edges) so no schema migration is needed; a full sweep runs when there are no LLM edges yet or every Nth run (configurable).
- **kNN candidate generation.** For each source page, fetch its top K=10 nearest neighbours from the Qdrant `pages` collection (excluding itself). Pairs already linked by a structural edge (`PART_OF` / `EVIDENCES` / `GROUNDS`) are pre-filtered out before the LLM call.
- **An LLM labeller** (a small `Extractor` seam mirroring the Phase 6 `answer/llm.py`: a `StubExtractor` for the hermetic tier and an `LLMExtractor` over the same `SYNTHESIS_*` config). One prompt per source page returns, for each candidate neighbour, a label in `{RELATED_TO, PREREQUISITE_FOR, NONE}`, a confidence `0.0..1.0`, and (for `PREREQUISITE_FOR`) a direction.
- **Provenance-aware edge upsert** in `compendium/graph/`: write `RELATED_TO` / `PREREQUISITE_FOR` with the full provenance property set; never overwrite a `extracted_by="curator"` edge; refresh provenance on an existing `extracted_by="llm"` edge. Reuses the node-resolution rule from `graph/links.py` (source pages → `:Source` keyed by `source_id`; concept/topic → `:Concept`/`:Topic` keyed by page id).
- **Threshold + logging.** Proposals below `curation.extract.min_confidence` (default `0.7`) are dropped. Every proposal is logged via structlog with its disposition: `accepted` / `dropped-by-confidence` / `dropped-by-collision` / `written`.
- **Config.** A new `curation.extract` block: `enabled` (default `true`), `min_confidence` (`0.7`), `top_k_neighbours` (`10`), `full_sweep_every` (runs). LLM endpoint/model/key reuse `synthesis:`.
- **An operational document** `docs/operations/edge-extraction.md` and a **Phase 8 (v0.2) smoke section**.
- **The CLAUDE.md exclusion line** "Not automated semantic-edge extraction" is updated to point at ADR-010 with the per-type qualifier.

## Capabilities

### New Capabilities

- `autonomous-edge-extraction`: the `from_extracted_edges` generator (`compendium/curate/extract.py`) run inside `compendium curate run`; the kNN-from-Qdrant candidate step with structural-edge pre-filtering; the `Extractor` LLM seam (one prompt per source page) labelling pairs as `RELATED_TO` / `PREREQUISITE_FOR` / `NONE` with confidence; the provenance-aware Memgraph edge upsert that never overwrites curator edges and refreshes LLM edges; the confidence threshold and per-proposal structlog; the change-detection watermark + periodic full sweep; `docs/operations/edge-extraction.md`.

### Modified Capabilities

<!-- ADR-009's curator-driven model is preserved for SYNTHESIZES
(lifecycle-owned) and CONTRADICTS (curator-only). The fast-loop graph
expansion (ADR-009) is unchanged in mechanism but now has more
RELATED_TO/PREREQUISITE_FOR edges to walk. `compendium graph link`,
`graph rebuild`, and `graph status` are unchanged; status simply shows
non-zero counts on the two extracted edge types. No retrieval contract
change. -->

## Impact

- **New code/files:** `compendium/curate/extract.py` (the generator + change detection + candidate step), an `Extractor` seam + prompts (in `extract.py` or a small `compendium/curate/extract_llm.py`), provenance-aware upsert in `compendium/graph/schema.py` (or `links.py`), `docs/operations/edge-extraction.md`.
- **Modified files:** `compendium/curate/run.py` (invoke the generator, count its writes in the report), `compendium/graph/schema.py` / `browse.py` (provenance upsert + structural-collision and curator-edge queries), `config/settings.yaml` + `compendium/config.py` (the `curation.extract` block), `tests/manual/smoke_test.md`, `README.md`, `CLAUDE.md` (status + the reversed exclusion line), `docs/Compendium.md` (ADR-010 status note), `docs/COMPENDIUM_V0.2_BUILD.md` Status.
- **No schema migration.** Provenance lives on Memgraph relationship properties; the change-detection watermark derives from the graph. No new PostgreSQL tables.
- **No new runtime dependency.** Reuses the `neo4j` Bolt driver, the `qdrant-client`, and the `SYNTHESIS_*` LLM seam.
- **Cost.** One LLM call per changed page per run (zero per-pair calls); zero when nothing changed and no full sweep is due. The stub extractor keeps the hermetic tier free of network calls.
- **Out of scope:**
  - **Autonomous `SYNTHESIZES`** — stays lifecycle-owned (the promote hook); autonomous extraction would race and double-write. Forever.
  - **Autonomous `CONTRADICTS`** — curator-only; a Shape-B "LLM suggests, curator approves" path is deferred to v0.3+.
  - **A new CLI verb.** Extraction runs inside `compendium curate run`; no `compendium extract` verb.
  - **Retrieval re-ranking on `extracted_by`/`confidence`.** Expansion walks the new edges as-is; weighting retrieval by provenance is a later concern.
  - **The `compendium serve` service unit** (ADR-012 later refactor) — unrelated to ADR-010; tracked separately.
