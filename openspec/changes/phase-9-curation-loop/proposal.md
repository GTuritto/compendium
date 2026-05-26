## Why

The graph exists (Phase 6) and retrieval, telemetry, and the ops console are built, but the graph does nothing for retrieval quality yet and the wiki does not improve from use. ADR-009 is the compounding mechanism: a **fast loop** that walks the graph at query time to surface related pages, and a **slow loop** that turns query gaps and graph weaknesses into a prioritized curation queue the curator drains into new pages. Phase 9 closes that loop. It is the phase that makes "every source you ingest improves every future query" literally true: a gap a query exposed becomes a signal, becomes a synthesized page, becomes graph edges, which improve the next replay of that query.

## What Changes

- **Fast loop (per query).** The Phase 5 pipeline, after RRF fusion, walks Memgraph from the top fused pages via the semantic edges (`RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`) with a hop limit and relevance decay, merges the expanded pages into the ranked list with a separate weighted score component, and records it in `query_traces.graph_expansion` (null until now). It no-ops gracefully when there are no semantic edges or Memgraph is unreachable.
- **Slow loop (on demand).** `compendium curate run` performs one analysis pass: it aggregates low-coverage / fallback queries (`low_coverage_query`, `gap`), concepts with too few `GROUNDS` edges (`thin_grounding`), concepts not attached to a topic (`dangling_concept`), and unresolved `CONTRADICTS` edges (`unresolved_contradiction`) into prioritized `graph_curation_signals` rows, and records the pass in `graph_analysis_runs`. No daemon — operator-triggered, matching the stack discipline.
- **Curator actions.** `compendium curate list` shows open signals; `compendium curate synth <signal-id>` triggers a synth pre-populated from the signal payload (producing a draft page revision); promoting that page (the Phase 7 `page promote` path) marks the signal `addressed` with its `addressed_revision_id` and adds `SYNTHESIZES` edges from the new page. `compendium graph link <from> <to> --type {RELATED_TO,PREREQUISITE_FOR,SYNTHESIZES,CONTRADICTS}` lets the curator add semantic edges by hand (no automated extraction in v0.1).
- **TUI.** The Phase 8 curation-queue screen gains actions: select a signal, trigger its synth, and reflect `addressed` state — closing the loop in the console; promotion uses the existing path.

## Capabilities

### New Capabilities

- `curation-loop`: ADR-009's two loops and the curator workflow — query-time graph expansion logged in the trace, the on-demand slow-loop signal generator, the signal-to-synth-to-promotion curator path, curator-driven semantic edges, and the TUI curation actions.

### Modified Capabilities

<!-- The retrieval pipeline gains an expansion step and the TUI curation screen
gains actions, but both are additive over existing behavior; the changes are
specified as new requirements under curation-loop rather than as deltas. The
graph_curation_signals / graph_analysis_runs tables and the curation enums exist
from Phase 1. -->

## Impact

- **New code:** `compendium/curate/` — the slow-loop signal generator and the synth-from-signal flow; graph-expansion logic in `compendium/retrieve/` (a new module + a hook in `pipeline.run`); a semantic-edge writer in `compendium/graph/`; `compendium curate {run,list,synth}` and `compendium graph link` CLI subcommands; curation actions on the Phase 8 TUI screen.
- **New repository functions:** insert/list/update `graph_curation_signals`, insert/complete `graph_analysis_runs`, and the reads the slow loop needs (low-coverage traces, concept grounding counts).
- **No schema migration.** `graph_curation_signals`, `graph_analysis_runs`, the `curation_signal_kind` / `curation_signal_status` enums, and `query_traces.graph_expansion` all exist from Phase 1.
- **Config:** a `curation` block (thin-grounding threshold, low-coverage threshold) and a `graph_expansion` block (hop limit, decay, weight) in `config/settings.yaml`.
- **Out of scope** (later / v0.2): a background scheduler for the slow loop (operator-triggered in v0.1); automated semantic-edge extraction (ADR-009 defers it); composed/LLM answers; Phase 10's golden-dataset regression harness (which will replay these traces).
