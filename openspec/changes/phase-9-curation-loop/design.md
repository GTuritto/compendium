## Context

This change implements Phase 9 (knowledge graph curation loop, workstream G2) of `docs/COMPENDIUM_BUILD.md`, the realization of ADR-009. It depends on Phase 5 (the retrieval pipeline and `query_traces`), Phase 6 (Memgraph and the typed-edge schema), Phase 7 (the `page promote` primitive and trace replay), and Phase 8 (the curation-queue screen to extend). The loops, edge semantics, signal kinds, and payload shapes are specified in `docs/Compendium.md` ADR-009 and the curation-schema section, and are implemented faithfully.

ADR-009 is the governing decision. Two loops over one Memgraph: a fast query-time loop that expands the ranked list, and a slow periodic loop that turns gaps and graph weaknesses into curator signals. The compounding behavior the whole project bets on lives here.

## Goals / Non-Goals

**Goals:**

- Query-time expansion that walks semantic edges from the top results and is logged in `query_traces.graph_expansion`.
- An on-demand slow loop that writes prioritized `graph_curation_signals` and a `graph_analysis_runs` record.
- The curator path: signal → synth → promote, with the signal marked `addressed` and the graph updated, such that a replay of the original query improves.
- Curator-driven semantic edges (explicit annotation + auto-`SYNTHESIZES` on promotion).

**Non-Goals:**

- A background scheduler/daemon for the slow loop (operator-triggered in v0.1; the config interval documents intent only).
- Automated semantic-edge extraction (ADR-009 defers to v0.2).
- Composed/LLM answers; the golden-dataset regression harness (Phase 10).
- Any schema migration (the tables and enums exist).

## Decisions

### Decision: the slow loop is an on-demand command, not a daemon

`compendium curate run` performs exactly one analysis pass and returns. It opens a `graph_analysis_runs` row, generates signals, sets `signal_count`/`summary`, and completes the row. This matches the stack discipline (no Kafka/Airflow/cron/daemon in v0.1); `loops.slow_loop_interval_seconds` stays in config as documented intent and as the value a future scheduler or the Phase 8 TUI would use, but nothing runs it automatically. Re-running is idempotent in spirit: a signal whose underlying condition already has an open signal is not duplicated (dedup by kind + a stable key in the payload).

### Decision: signal generators, one per kind, reading Postgres + Memgraph

The slow loop runs a set of independent generators:

- `low_coverage_query` / `gap` — from `query_traces`: queries below `page_coverage_threshold` or with `fallback_to_chunks` / non-empty `gaps`, aggregated by query text; the payload carries `query_trace_ids` and the observed coverage.
- `thin_grounding` — concepts with fewer than `curation.thin_grounding_min` `GROUNDS` edges (counted in Memgraph); payload `{page_id, grounds_count, expected_threshold}`.
- `dangling_concept` — `:Concept` nodes with no `PART_OF` edge to a `:Topic`; payload `{page_id, candidate_topic_ids}`.
- `unresolved_contradiction` — `CONTRADICTS` edges with no `resolution_page_id`; payload `{page_a, page_b, edge_id}`.

Each generator is a pure-ish function returning candidate signals; the runner dedups against open signals and inserts. Generators that need Memgraph degrade gracefully (skipped with a note in the run summary) when it is unreachable, so the loop still produces the Postgres-derived signals.

### Decision: fast-loop expansion is a post-fusion step in the existing pipeline

In `pipeline.run`, after `reciprocal_rank_fusion` produces the fused pages and before coverage scoring's result is finalized, an expansion step walks Memgraph from the top-`expansion.seed_k` fused pages over `RELATED_TO`/`PREREQUISITE_FOR`/`SYNTHESIZES` edges up to `expansion.max_hops`, scoring each reached page by `weight * decay^hop` and merging it into the ranked list (a page already present keeps the higher of its fused and expansion-augmented score). The expansion (seeds, reached pages, edges, contribution) is recorded in `query_traces.graph_expansion`. It is gated by config and by graph reachability: with expansion disabled, no semantic edges, or Memgraph down, the step is a no-op and `graph_expansion` stays null, so existing Phase 5 behavior is unchanged until the curator has built edges. Coverage is still computed on the page set; expansion adds candidates, it does not change the coverage definition.

### Decision: synth-from-signal reuses the existing synthesizer; promotion closes the loop

`compendium curate synth <signal-id>` reads the signal payload, derives the target (a `missing_concept` name for `gap`/`low_coverage_query`, or the under-grounded/dangling page for the page-keyed kinds), and calls the existing `synthesize_concept` (Phase 3) to produce a draft revision — no new synthesis logic. The signal is moved to `in_progress`. Promotion of the resulting page goes through the Phase 7 `page promote` path; on promotion the system marks the signal `addressed` with the new `addressed_revision_id` and adds `SYNTHESIZES` edges from the new page to the sources/pages it drew from. This keeps one promotion primitive and one synthesizer.

### Decision: semantic edges are curator-explicit, plus auto-SYNTHESIZES

`compendium graph link <from-slug> <to-slug> --type {RELATED_TO,PREREQUISITE_FOR,SYNTHESIZES,CONTRADICTS}` writes a single typed edge (with `weight`/`created_at`, and `resolution_page_id` accepted for `CONTRADICTS`) via the Phase 6 `upsert_edge`. This is the only way `RELATED_TO`/`PREREQUISITE_FOR`/`CONTRADICTS` are created in v0.1; `SYNTHESIZES` is additionally created automatically on synth-from-signal promotion. No automated extraction — ADR-009 defers it. The edge writer validates both endpoints exist and the type is one of the four semantic kinds (the automatic kinds stay owned by Phase 6 projection).

### Decision: TUI curation actions extend the Phase 8 read-only screen

The curation-queue screen gains: select a signal (row), trigger `curate synth` for it in a worker, and reflect status transitions (`open` → `in_progress` → `addressed`). It reuses the `compendium/curate/` functions (no logic in the screen) and the existing promotion path. The screen stays a thin view over the same engine the CLI uses, so the loop is drivable either way.

## Risks / Trade-offs

- **Expansion adds latency and a Memgraph dependency to every query** → Gated by config and reachability; a no-op when there are no semantic edges (the common early state). The walk is hop-limited and seeded by only the top-k pages.
- **Expansion is a no-op until the curator builds edges, so "replay improves" needs edges first** → Accepted and is the point: the acceptance flow promotes a synth'd page (auto-`SYNTHESIZES`) and/or links edges, then replays; the improvement is the loop working, not a static feature.
- **Slow-loop signal spam** → Dedup against open signals by kind + payload key; priority ordering so the curator drains the most valuable first; re-runs do not pile duplicates.
- **Generators querying both stores can partially fail** → Each generator is independent and the run summary records which ran; a Memgraph outage still yields the Postgres-derived signals rather than aborting the pass.
- **No scheduler means the loop only runs when invoked** → Accepted for v0.1; documented, and the TUI/CLI make invocation easy.

## Migration Plan

No schema migration. Add a `curation` block (`thin_grounding_min`, `low_coverage_threshold`) and a `graph_expansion` block (`enabled`, `seed_k`, `max_hops`, `decay`, `weight`) to `config/settings.yaml`. Rollback is removing `compendium/curate/`, the expansion module + the `pipeline.run` hook, the `graph link` writer, the new CLI subcommands, the TUI actions, and the new repository functions; data and prior phases are untouched, and `graph_expansion` simply returns to always-null.

## Open Questions

- **Expansion defaults.** Proposed `seed_k=3`, `max_hops=2`, `decay=0.5`, `weight=0.3` (so expansion never outranks a strong direct hit), `enabled=true`. Confirm the defaults at the review gate; they are tunable config and get validated against the Phase 10 golden set.
- **`gap` vs `low_coverage_query` overlap.** Both derive from weak queries; the plan emits `low_coverage_query` for a single weak query and `gap` when several weak queries cluster on missing concepts. Confirm that split, or collapse to one kind.
