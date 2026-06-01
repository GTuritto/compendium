# Autonomous semantic-edge extraction

The slow curation loop autonomously proposes and writes two semantic edge types
into Memgraph — `RELATED_TO` and `PREREQUISITE_FOR` — so the fast-loop graph
expansion densifies without curator effort. v0.2 Phase 8, shipping ADR-010. It
selectively reverses the v0.1 "Not automated semantic-edge extraction" line for
exactly the two edge types where the LLM is trustworthy, and tags every edge
with provenance so the decision stays reversible and auditable.

## Where it runs

The extractor is a fifth generator, `from_extracted_edges`, inside
`compendium curate run` (and therefore the scheduled curation daemon, ADR-012).
It runs after the four ADR-009 signal generators, inside the same Memgraph
session, and is **skip-graceful**: if Memgraph or Qdrant is unreachable, or
`curation.extract.enabled` is false, the run continues without it. There is no
`compendium extract` CLI verb — extraction is part of the slow loop.

## The two edge types (and why only those)

| Edge type | v0.2 source |
| --- | --- |
| `RELATED_TO` | LLM extractor + curator |
| `PREREQUISITE_FOR` | LLM extractor + curator |
| `SYNTHESIZES` | curator-driven via the promote hook (`curate/lifecycle`) — unchanged |
| `CONTRADICTS` | curator-only via `compendium graph link` — unchanged; v0.3+ for a suggest-then-approve shape |

`SYNTHESIZES` is owned by the lifecycle (the promote hook writes it); autonomous
extraction would race and double-write. `CONTRADICTS` makes the strongest claim
(two sources disagree) and feeds the contradiction curation generator — the
curator stays in front of it.

## How a run works

For each concept/source page in scope (see change detection below):

1. **kNN.** Pull the top `curation.extract.top_k_neighbours` (default 10)
   nearest neighbours from the Qdrant `pages` collection (self excluded).
2. **Structural pre-filter.** Drop neighbours already connected by a structural
   edge (`PART_OF` / `EVIDENCES` / `GROUNDS`, within 1–2 hops) — the projection
   already encodes those, and spending an LLM call on them would be wasted.
3. **One LLM call.** Ask the LLM (prompt `extract-v1`, over the `SYNTHESIS_*`
   config) to label each remaining pair `RELATED_TO`, `PREREQUISITE_FOR`, or
   `NONE` with a confidence and, for `PREREQUISITE_FOR`, a direction. One call
   per source page, never one per pair — cost scales with turnover, not size.
4. **Threshold + write.** Drop labels below `curation.extract.min_confidence`
   (default `0.7`). Write the rest to Memgraph with provenance.

Set `COMPENDIUM_SYNTH_STUB=1` to run the deterministic stub labeller (no network,
no cost) — the hermetic test tier and a free smoke walk run this way.

## Provenance, weight, and reversibility

Every extracted edge carries relationship properties:

```cypher
(:Page)-[:RELATED_TO {
  extracted_by: "llm",
  model: "<llm identifier>",
  confidence: 0.0..1.0,
  extracted_at: "<iso8601>",
  source_revision_id: "<uuid>",   // the page revision that triggered it
  weight: <confidence>            // = confidence, so expansion down-weights weak edges
}]->(:Page)
```

Curator edges (`extracted_by="curator"`, written by `compendium graph link`) are
**never overwritten**; a labelled pair that already has a curator edge is logged
`dropped-by-collision`. An existing LLM edge is **refreshed** in place on
re-extraction (no duplicates). `RELATED_TO` is symmetric (one edge per unordered
pair, canonicalised); `PREREQUISITE_FOR` is directed.

Because provenance is on the edge, the decision is reversible by predicate:

```cypher
-- raise the confidence bar
MATCH ()-[r {extracted_by:"llm"}]-() WHERE r.confidence < 0.85 DELETE r;
-- wipe a model generation
MATCH ()-[r {extracted_by:"llm"}]-() WHERE r.model = "<old model>" DELETE r;
-- audit what the LLM added
MATCH ()-[r {extracted_by:"llm"}]-() RETURN r.extracted_at, r.confidence ORDER BY r.extracted_at DESC;
-- the trusted subset only
MATCH ()-[r {extracted_by:"curator"}]-() RETURN r;
```

`compendium graph rebuild` drops and reprojects structural + curator edges; LLM
edges are re-created on the next `curate run` (they are derived, like the rest of
the graph).

## Change detection and the full sweep

The "last extraction" watermark is the maximum `extracted_at` over
`extracted_by="llm"` edges in Memgraph (no PostgreSQL migration). A run processes
pages whose current revision is newer than the watermark. A **full sweep** (all
concept/source pages) runs when there are no LLM edges yet (cold start) or every
`curation.extract.full_sweep_every` runs (default 24). If the curator prunes all
LLM edges, the watermark resets and the next run full-sweeps.

## Cost model

One LLM call per changed page per run; zero when nothing changed and no full
sweep is due. A full sweep is `O(pages)` calls and is infrequent. The cadence and
the neighbour count (`top_k_neighbours`) bound the cost.

## Logging

Every proposal is logged via structlog with a disposition: `written`,
`refreshed`, `dropped-by-confidence`, or `dropped-by-collision`. The run report
(`CurateReport.extracted_edges`) and the `graph_analysis_runs` summary carry the
per-disposition counts.

## Configuration

```yaml
curation:
  extract:
    enabled: true
    min_confidence: 0.7       # labels below this are dropped
    top_k_neighbours: 10      # Qdrant neighbours per source page
    full_sweep_every: 24      # re-sweep all pages every Nth run (cold start always sweeps)
```

The LLM endpoint/model/key reuse the `synthesis:` block.

## Out of scope (v0.2 Phase 8)

- Autonomous `SYNTHESIZES` (lifecycle-owned) and `CONTRADICTS` (curator-only; v0.3+).
- A `compendium extract` CLI verb (runs inside `curate run`).
- Retrieval re-ranking / filtering by `extracted_by` or `confidence` (expansion
  walks the edges as-is, weighted by `weight=confidence`).
