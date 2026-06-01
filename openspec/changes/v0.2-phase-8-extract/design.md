## Context

This change implements Phase 8 of `docs/COMPENDIUM_V0.2_BUILD.md` and ships ADR-010. It depends on: the Phase 9 slow loop (`compendium/curate/run.py` and its graph-backed generators), the Phase 6 Memgraph layer (`compendium/graph/` — `schema.upsert_edge`, the node-resolution rule in `links.py`, `browse.walk_semantic`), the Qdrant `pages` collection populated by Phase 4 (kNN source), and the `SYNTHESIS_*` LLM seam (as used by `answer/llm.py`). It does not depend on later work.

ADR-010 is the contract. The whole bet: densify the two edge types where the LLM is trustworthy, tag every edge with honest provenance so the decision is reversible by predicate, and bound cost to one LLM call per changed page per run.

## Goals / Non-Goals

**Goals:**

- A `from_extracted_edges` generator in `compendium/curate/` invoked by `compendium curate run`, graph-backed and skip-graceful.
- For each changed page (+ periodic full sweep): top-K=10 Qdrant neighbours, structural-collision pre-filter, one LLM call labelling each pair `RELATED_TO` / `PREREQUISITE_FOR` / `NONE` + confidence.
- Provenance-aware writes: `extracted_by="llm"`, `model`, `confidence`, `extracted_at`, `source_revision_id`, `weight`; never overwrite curator edges; refresh LLM edges.
- Threshold drop (`min_confidence` default 0.7) and per-proposal structlog.
- No schema migration; bounded cost; hermetic tier uses a stub extractor.

**Non-Goals:**

- Autonomous `SYNTHESIZES` (lifecycle-owned) or `CONTRADICTS` (curator-only; v0.3+ Shape B).
- A new CLI verb (runs inside `curate run`).
- Retrieval weighting/filtering by provenance.
- Per-pair LLM calls.

## Decisions

### Decision: the extractor is a generator inside the slow loop, not a new verb

`from_extracted_edges` slots into `compendium/curate/run.py` alongside the four ADR-009 generators, after the graph-reachability check, sharing the `graph_connection()` and the skip-graceful pattern. It is invoked by `compendium curate run` and therefore by the scheduled daemon (ADR-012). Its writes are counted in the `CurateReport` (a new `extracted_edges` field or folded into `by_kind`).

**Alternative considered:** a standalone `compendium extract` verb. Rejected — the slow loop is the documented home (ADR-010), the daemon already runs it on cadence, and a separate verb duplicates the run scaffolding.

### Decision: change detection derives the watermark from the graph (no migration)

The "last extraction" watermark is `max(r.extracted_at)` over `extracted_by="llm"` relationships in Memgraph. Changed pages are those whose current `wiki_page_revisions` row is newer than the watermark. A **full sweep** (all pages) runs when there are no LLM edges yet (cold start) or every `curation.extract.full_sweep_every` runs (a counter persisted in the `graph_analysis_runs` summary, or derived from run ordinal). This keeps Phase 8 migration-free.

**Alternative considered:** a dedicated `edge_extraction_state` table in PostgreSQL. Rejected for v0.2 — it adds a migration for one timestamp; the graph already holds the authoritative `extracted_at`. A table can be added later if the derived watermark proves insufficient (e.g., when LLM edges are pruned).

### Decision: one LLM call per source page, labelling all K neighbours at once

The prompt presents the source page (title + a bounded body excerpt) and the K candidate neighbours (numbered, with titles + excerpts), and asks for a JSON array of `{neighbour, label, confidence, direction?}`. This is one call per page (ADR-010's cost cap), not K calls. The labeller is an `Extractor` seam: `StubExtractor` (deterministic, hermetic tier) and `LLMExtractor` (OpenAI-compatible over `SYNTHESIS_*`), mirroring `answer/llm.py`. Token counts are not persisted (no `ask_traces` analogue) — structlog records dispositions.

**Alternative considered:** one call per pair. Rejected by ADR-010 on cost (scales with K×pages instead of pages).

### Decision: structural-collision pre-filter before the LLM call

Before labelling, drop candidate pairs already connected by a structural edge (`PART_OF` / `EVIDENCES` / `GROUNDS`) in either direction — a Cypher existence check per pair (or one batched query per source page). This avoids spending the LLM budget on pairs the projection already knows are related, and avoids semantic edges shadowing structural ones.

**Alternative considered:** filter after labelling. Rejected — pre-filtering shrinks the prompt and the cost.

### Decision: provenance upsert that protects curator edges

The write is a `MERGE` on `(a)-[r:TYPE]->(b)` guarded so that: if `r` exists with `extracted_by="curator"`, leave it untouched (log `dropped-by-collision`); otherwise set the full LLM provenance property set (creating or refreshing). `RELATED_TO` is written once per unordered pair (symmetric convention, matching `graph link`); `PREREQUISITE_FOR` is directed per the LLM's `direction`. `weight` is set to the confidence so the fast-loop expansion naturally down-weights low-confidence edges (the existing curator default stays `1.0`).

**Alternative considered:** fixed `weight=1.0` for LLM edges. Rejected — confidence-as-weight gives expansion a free quality signal at no extra cost; curator edges keep `1.0`.

### Decision: the source-page set is the Qdrant `pages` collection (concept + source)

Extraction iterates the pages indexed in Qdrant `pages` (concept and source pages), which is also where the neighbours come from. Topic pages and chunks are out (topics are structural groupings; chunks are not pages). This matches the retrieval substrate the expansion walks.

**Alternative considered:** concept pages only. Rejected — source pages are legitimate retrieval targets and relate to concepts; restricting to concepts would miss source↔concept `PREREQUISITE_FOR`/`RELATED_TO` edges.

## Risks / Trade-offs

- **LLM false positives densify the graph with wrong edges.** Mitigated by the 0.7 confidence floor, the `extracted_by="llm"` tag (auditable / reversible by predicate), and confidence-as-weight (low-confidence edges contribute little to expansion). The curator can raise the bar or wipe a model generation with one Cypher statement.
- **Hermetic tests can't judge label quality.** The stub extractor returns deterministic labels, so tests verify mechanism (candidate generation, pre-filter, threshold, provenance write, curator-edge protection, watermark), not semantic accuracy. Real-model quality is the curator's smoke/observation, same posture as Phases 1/5/6.
- **Derived watermark + pruning interaction.** If the curator prunes all LLM edges, the watermark resets and the next run full-sweeps. Acceptable (a sweep is bounded by corpus size, one call per page). Documented.
- **Directionality of `PREREQUISITE_FOR`.** Wrong direction is a real error mode; the prompt asks for direction explicitly and the write respects it. `RELATED_TO` is symmetric so direction is moot.
- **Cost on a full sweep of a large corpus.** One call per page; a full sweep is O(pages) calls. Bounded and infrequent (cold start or every Nth run); the cadence is configurable.

## Migration Plan

No schema migration. The feature is additive: new code in `compendium/curate/` and `compendium/graph/`, a config block, and Memgraph relationship properties on the two extracted edge types. `compendium graph rebuild` still drops and reprojects structural edges and curator semantic edges; LLM edges are re-created on the next `curate run` (they are derived, like the rest of the graph). Rollback is removing the generator + the config block, and optionally `MATCH ()-[r {extracted_by:"llm"}]-() DELETE r` to clear extracted edges.

## Open Questions — resolved at the review gate (2026-06-01)

All resolved by accepting the recommendation.

1. **Change-detection watermark.** RESOLVED: derive from the graph (`max(extracted_at)` over LLM edges) — no migration.
2. **Full-sweep cadence.** RESOLVED: cold start + every `full_sweep_every` runs (default 24).
3. **`weight` of LLM edges.** RESOLVED: `weight = confidence` (curator edges stay `1.0`).
4. **Source-page set.** RESOLVED: concept + source pages (the Qdrant `pages` collection).
5. **Labeller module + prompt id.** RESOLVED: `compendium/curate/extract.py` + an `Extractor` seam (stub + LLM over `SYNTHESIS_*`), prompt id `extract-v1`.
6. **Report shape.** RESOLVED: `extracted_edges: {written, refreshed, dropped_confidence, dropped_collision}` on `CurateReport` and the run summary.
