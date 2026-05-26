# Phase 9 — Knowledge graph curation loop: Implementation Plan

Date: 2026-05-26
Branch: `phase-9-curation-loop` (off `main`)
OpenSpec change: `openspec/changes/phase-9-curation-loop/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 9;
[docs/Compendium.md](../docs/Compendium.md) ADR-009.

## Goal

The graph informs both retrieval and synthesis. The fast loop runs per query;
the slow loop runs on demand and produces a curation queue. The acceptance loop:
a query with a gap → a signal → a synth'd draft that lint-passes and cites
chunks → promotion that updates the graph → a replay of the original query that
improves.

## Why this plan exists

This is the compounding mechanism the whole project bets on. The plan locks four
decisions confirmed at the review gate: (1) the slow loop is an on-demand
`compendium curate run`, not a daemon (stack discipline); (2) the fast loop is a
post-fusion expansion step integrated into the Phase 5 pipeline, gated by config
+ Memgraph reachability and a no-op until semantic edges exist; (3) semantic
edges are curator-explicit (`compendium graph link`) plus auto-`SYNTHESIZES` on
synth-from-signal promotion — no automated extraction (ADR-009 defers it); (4)
the CLI is the engine and the Phase 8 curation screen gains actions over it.

## Branch + commit strategy

- Create `phase-9-curation-loop` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 9a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 9 complete — knowledge graph curation loop`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### 9a — Slow loop: signals + runs

**Purpose:** Turn gaps and graph weaknesses into a prioritized queue, on demand.

**Tasks:**

1. Config `curation` block (`thin_grounding_min`, `low_coverage_threshold`).
2. Repository: insert/list/update `graph_curation_signals` (dedup open by kind +
   payload key), open/complete `graph_analysis_runs`, plus generator reads.
3. `compendium/curate/signals.py`: one generator per kind
   (`low_coverage_query`/`gap` from `query_traces`; `thin_grounding` /
   `dangling_concept` / `unresolved_contradiction` from Memgraph).
4. `compendium/curate/run.py`: the runner (open run → generators, graph ones
   skipped gracefully if Memgraph down → dedup + insert → complete run).
5. `compendium curate {run,list}` CLI.

**Files added:** `compendium/curate/{__init__,signals,run}.py`
**Files modified:** `config/settings.yaml`, `compendium/db/repository.py`, `compendium/__main__.py`
**Decision flagged:** on-demand, no daemon; dedup against open signals.

### 9b — Fast loop: query-time expansion

**Purpose:** Walk the graph from top results and improve the ranking.

**Tasks:**

1. Config `graph_expansion` block (`enabled`, `seed_k`, `max_hops`, `decay`, `weight`).
2. Graph walk over `RELATED_TO`/`PREREQUISITE_FOR`/`SYNTHESIZES` from seed ids
   (reached pages + hop distance + edges).
3. `compendium/retrieve/expansion.py`: score (`weight * decay^hop`) and merge;
   build the `graph_expansion` trace payload.
4. Hook into `pipeline.run` after fusion; gate by config + reachability (no-op →
   `graph_expansion` null).

**Files added:** `compendium/retrieve/expansion.py` (+ graph walk in `compendium/graph/`)
**Files modified:** `config/settings.yaml`, `compendium/retrieve/pipeline.py`
**Decision flagged:** integrated into the standard query path; no-op without edges.

### 9c — Curator path: synth-from-signal + semantic edges

**Tasks:**

1. `compendium/curate/synth.py`: derive the target from a signal payload, call
   `synthesize_concept`, move the signal `in_progress`.
2. Extend the Phase 7 `promote` path: addressing a signal sets `addressed` +
   `addressed_revision_id` and adds `SYNTHESIZES` edges.
3. `compendium/graph/links.py`: `link(from, to, type)` via `upsert_edge`,
   validating endpoints + semantic type.
4. `compendium curate synth <id>` and `compendium graph link` CLI.

**Files added:** `compendium/curate/synth.py`, `compendium/graph/links.py`
**Files modified:** `compendium/trace/promote.py`, `compendium/__main__.py`
**Decision flagged:** explicit edges + auto-`SYNTHESIZES`; one synthesizer, one
promotion primitive.

### 9d — TUI curation actions

**Tasks:**

1. Extend `compendium/tui/screens/curation.py`: select a signal, trigger
   `curate synth` in a worker, reflect status transitions; reuse `compendium/curate/`
   and the `compendium/tui/data.py` provider layer.

**Files modified:** `compendium/tui/screens/curation.py`, `compendium/tui/data.py`
**Decision flagged:** the screen is a thin view over the same engine the CLI uses.

### 9e — Tests and acceptance

**Tasks:**

1. Unit: generators (low-coverage from fixture traces; thin-grounding/dangling
   from a small graph); dedup; expansion scoring/merge (pure).
2. Integration (skip if stores down, stubs): `curate run` writes signals + a run
   row; re-run no duplicates; Memgraph-down still yields Postgres signals.
3. Expansion: with a `RELATED_TO` edge, a query expands + logs `graph_expansion`;
   without, no-op + null.
4. Acceptance loop end-to-end (see Goal).
5. TUI Pilot: curation screen triggers a synth and reflects the status change.
6. Append the Phase 9 smoke section; run it.

**Files added:** `tests/test_curation.py`
**Files modified:** `tests/test_tui.py` (curation action), `tests/manual/smoke_test.md`

## Final file tree after Phase 9

```text
compendium/
  curate/
    __init__.py          NEW
    signals.py           NEW — per-kind signal generators
    run.py               NEW — on-demand slow-loop runner
    synth.py             NEW — synth-from-signal
  retrieve/
    expansion.py         NEW — fast-loop scoring/merge
    pipeline.py          MOD — post-fusion expansion hook
  graph/
    expand.py            NEW (or browse.py addition) — semantic-edge walk
    links.py             NEW — curator semantic-edge writer
  trace/promote.py       MOD — address signal + auto-SYNTHESIZES on promotion
  tui/screens/curation.py MOD — synth-from-signal action
  tui/data.py            MOD — curation action providers
  db/repository.py       MOD — signals/runs reads+writes
  __main__.py            MOD — `curate run|list|synth`, `graph link`
config/settings.yaml      MOD — curation + graph_expansion blocks
tests/
  test_curation.py       NEW
  test_tui.py            MOD
  manual/smoke_test.md   MOD — § Phase 9
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | signal generators | low-coverage trace → signal; thin-grounding/dangling from a small graph |
| 2 | unit | dedup | re-run yields no duplicate open signal |
| 3 | unit | expansion scoring | reached page scored `weight*decay^hop`; merged without displacing a strong direct hit |
| 4 | integration | curate run | signals + a completed `graph_analysis_runs` row; Memgraph-down still yields Postgres signals |
| 5 | integration | expansion on/off | `RELATED_TO` present → expands + logs `graph_expansion`; none → no-op + null |
| 6 | integration | acceptance loop | gap → signal → synth (lint-passes, cites chunks) → promote → addressed + `SYNTHESIZES` → replay improves |
| 7 | pilot | TUI curation | trigger synth from a signal; status transitions |

## Per-phase smoke test

Appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 9.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 9.1 | Slow loop | run an uncovered query, then `uv run python -m compendium curate run` | a `graph_analysis_runs` row; open signal(s) incl. a low-coverage/gap one |
| 9.2 | List signals | `uv run python -m compendium curate list` | open signals by priority with kind + summary |
| 9.3 | Synth from signal | `uv run python -m compendium curate synth <id>` | a draft concept page, lint-passes, cites chunks; signal `in_progress` |
| 9.4 | Promote closes loop | `uv run python -m compendium page promote <slug> --to canonical` | signal `addressed` with `addressed_revision_id`; a `SYNTHESIZES` edge added |
| 9.5 | Expansion + replay | `graph link` a related page, then `trace replay <original-id>` | replay shows the related/new page (improved ranking); `graph_expansion` populated on a fresh query |
| 9.6 | TUI | `compendium tui` → `c` → select a signal → trigger synth | synth runs; the signal's status updates in the queue |

## Out of scope for Phase 9 (do NOT build)

- A background scheduler/daemon for the slow loop (operator-triggered in v0.1).
- Automated semantic-edge extraction (ADR-009 defers to v0.2).
- Composed/LLM answers.
- The Phase 10 golden-dataset regression harness (which will replay these traces).

## Open questions — resolved at the review gate (2026-05-26)

1. **Slow-loop trigger.** RESOLVED: on-demand `compendium curate run`; no daemon.
2. **Fast-loop wiring.** RESOLVED: integrated into the Phase 5 pipeline; no-op
   without semantic edges / Memgraph.
3. **Semantic edges.** RESOLVED: explicit `compendium graph link` + auto-
   `SYNTHESIZES` on synth-from-signal promotion; no automated extraction.
4. **Curator UI.** RESOLVED: CLI engine + actions on the Phase 8 curation screen.
5. **Expansion defaults (to confirm during 9b).** Proposed `enabled=true`,
   `seed_k=3`, `max_hops=2`, `decay=0.5`, `weight=0.3`; tunable config, validated
   against the Phase 10 golden set.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 9 met.
- [ ] PR marked ready for review.
