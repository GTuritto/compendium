# Design — v0.3 Phase 1: contradiction candidates

## The suggestion path (no edge until approval)

    curate run
      └─ from_contradiction_candidates(conn, driver, qclient, cfg)
           watermark = latest contradiction_candidate signal created_at
           pages     = concept pages changed since (full sweep: cold start / Nth run)
           per page: neighbours = extract.nearest_neighbours (reused)
                     drop: any-edge-linked (structural_pairs | semantic_adjacent_ids)
                           or already-proposed pair (any signal status)
                     labels = contradictor.label_contradictions(...)  # contradict-v1
                     >= min_confidence -> insert_curation_signal(kind=contradiction_candidate,
                           payload={from_slug,from_title,to_slug,to_title,confidence,rationale})

    curate resolve <id> --approve            curate resolve <id> --drop
      └─ kind-dispatched approve action        └─ set_signal_status(dropped)
         contradiction_candidate:
           links.link(from_slug, to_slug, "CONTRADICTS")   # curator path, ADR-013 dual-write
           set_signal_status(addressed)

## Seams reused, not reopened

- `Extractor`-style seam: a `Contradictor` protocol + stub + real client over
  the **chat envelope** (`model_clients.chat`, review-#4 fix 1) and the
  registry (`get_model_client("contradictor")`, fifth role, same
  `COMPENDIUM_SYNTH_STUB`/umbrella flags).
- Neighbour pull: `extract.nearest_neighbours` (unchanged).
- Edge write: the existing curator path (`graph/links.link` →
  `semantic_edges.record_semantic_edge` → `schema.upsert_semantic_edge`), so
  ADR-013 persistence and curator protection hold by construction.
- Signals: the existing queue (`insert_curation_signal`, `set_signal_status`;
  the `dropped` status already exists in the enum).

## Resolved open questions

- **Q1**: add `contradiction_candidate` (migration `0014`); a *proposed*
  contradiction is never confused with a curator-noticed
  `unresolved_contradiction`.
- **Q2**: `curate resolve` is generic — drop for every kind now, approve via a
  per-kind action map with `contradiction_candidate` as the first entry; other
  kinds answer "approve is not defined for kind X" (synth stays the path for
  coverage signals).

## Bounds (identical to Phase 8)

One LLM call per changed concept page; K=10 neighbours; confidence threshold
0.7; every proposal logged (`written-as-signal` / `dropped-by-confidence` /
`dropped-by-collision` / `dropped-already-proposed`) and counted in the
`graph_analysis_runs` summary under `contradictions`.
