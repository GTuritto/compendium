# Tasks — phase-9-curation-loop

Implements Phase 9 of `docs/COMPENDIUM_BUILD.md` (ADR-009). No schema migration:
`graph_curation_signals`, `graph_analysis_runs`, the `curation_signal_kind` /
`curation_signal_status` enums, and `query_traces.graph_expansion` exist from
Phase 1. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. Slow loop: signals + runs (9a)

- [ ] 1.1 Config: add a `curation` block (`thin_grounding_min`, `low_coverage_threshold`) to `config/settings.yaml`
- [ ] 1.2 `compendium/db/repository.py`: insert/list/update `graph_curation_signals` (dedup an open signal by kind + payload key), open/complete `graph_analysis_runs`, and the reads the generators need (low-coverage traces; concept ids)
- [ ] 1.3 `compendium/curate/signals.py`: one generator per kind — `low_coverage_query`/`gap` (from `query_traces`), `thin_grounding` / `dangling_concept` / `unresolved_contradiction` (from Memgraph), each returning candidate signals with payloads
- [ ] 1.4 `compendium/curate/run.py`: the slow-loop runner — open a run, invoke generators (skip graph ones gracefully if Memgraph is down), dedup + insert signals, complete the run with count + summary
- [ ] 1.5 `compendium curate {run,list}` CLI subcommands

## 2. Fast loop: query-time expansion (9b)

- [ ] 2.1 Config: add a `graph_expansion` block (`enabled`, `seed_k`, `max_hops`, `decay`, `weight`)
- [ ] 2.2 `compendium/graph/browse.py` (or a new `expand.py`): walk semantic edges (`RELATED_TO`/`PREREQUISITE_FOR`/`SYNTHESIZES`) from seed page ids up to `max_hops`, returning reached pages with hop distance and the edges traversed
- [ ] 2.3 `compendium/retrieve/expansion.py`: score reached pages (`weight * decay^hop`) and merge into the fused list; build the `graph_expansion` trace payload
- [ ] 2.4 Hook into `compendium/retrieve/pipeline.run` after fusion; gate by config + Memgraph reachability (no-op → `graph_expansion` stays null); populate the trace

## 3. Curator path: synth-from-signal + semantic edges (9c)

- [ ] 3.1 `compendium/curate/synth.py`: derive the synth target from a signal payload, call `synthesize_concept`, move the signal to `in_progress`
- [ ] 3.2 On promotion (extend the Phase 7 `promote` path): if the page addresses a signal, mark it `addressed` with `addressed_revision_id` and add `SYNTHESIZES` edges from the new page
- [ ] 3.3 `compendium/graph/links.py`: `link(from_slug, to_slug, type, ...)` writing one semantic edge via the Phase 6 `upsert_edge`, validating endpoints + that the type is semantic
- [ ] 3.4 `compendium curate synth <id>` and `compendium graph link <from> <to> --type ...` CLI subcommands

## 4. TUI curation actions (9d)

- [ ] 4.1 Extend `compendium/tui/screens/curation.py`: select a signal row, trigger `curate synth` in a worker, reflect status transitions; reuse the `compendium/curate/` functions and the `compendium/tui/data.py` provider layer

## 5. Tests and acceptance (9e)

- [ ] 5.1 Unit: signal generators (low-coverage from fixture traces; thin-grounding/dangling from a small graph); dedup; expansion scoring/merge (pure)
- [ ] 5.2 Integration (skip if stores unreachable, stubs): `curate run` writes signals + a run row; re-run does not duplicate; Memgraph-down still yields Postgres signals
- [ ] 5.3 Expansion: with a `RELATED_TO` edge present, a query expands and logs `graph_expansion`; with none, it is a no-op and `graph_expansion` is null
- [ ] 5.4 Acceptance loop: query with a gap → `curate run` surfaces a matching signal → `curate synth` produces a lint-passing draft citing chunks → promote → signal `addressed`, `SYNTHESIZES` edge added → replay of the original query improves
- [ ] 5.5 TUI: Pilot test — curation screen triggers a synth from a selected signal and reflects the status change
- [ ] 5.6 Append the Phase 9 smoke section to `tests/manual/smoke_test.md`; run it
- [ ] 5.7 **Acceptance:** the full ADR-009 loop passes per § Phase 9. `uv run pytest` passes
