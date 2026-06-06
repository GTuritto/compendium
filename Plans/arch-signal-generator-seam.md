# Arch fix 4 — SignalGenerator registry: Implementation Plan

Date: 2026-06-06
Branch: `arch/signal-generators` (off `main`)
OpenSpec change: `openspec/changes/arch-signal-generator-seam/`
Spec source: architecture review #4 (candidate 4; the standing "fix 5" from
review #3). Preserves ADR-009 / ADR-010. Independent of the other pending fixes.

## Goal

Consolidate the slow-loop signal generators — today free functions with
mismatched signatures plus hardwired runner glue and a hardcoded kind-list —
into one `SignalGenerator` registry the runner iterates, the same shape as fix 2
(`EdgeType`) and fix 3 (`PageKind`). The autonomous extractor stays a separate
step. Behaviour-preserving.

## Why this plan exists

It locks in that this is a **rule relocation, not a behaviour change**: the same
signals (kind / priority / payload), the same dedup, the same skip-on-unreachable
semantics, and the same `graph_analysis_runs` summary. It also pins the one
deliberate improvement (per-generator try/except instead of one block) and the
one explicit boundary (the extractor is NOT a signal generator).

## Branch + commit strategy

- Create `arch/signal-generators` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch4a — SignalGenerator registry`, `Arch4b — run.py iterates`, …), green at HEAD.
- Final commit: `Arch fix 4 complete — SignalGenerator registry`.
- Commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — The registry + context

**Purpose:** Land the single home for the generators with zero runner change.

**Tasks:** `signal_generator.py` (`Signal` NamedTuple, `GenerationContext`, `SignalGenerator` record, `REGISTRY`); the four generators adapted to `generate(ctx)` (bodies stay in `signals.py`, referenced from the registry); `signals.py` re-exports `Signal`; `test_signal_generator.py`.

**Files added:** `compendium/curate/signal_generator.py`, `tests/test_signal_generator.py`
**Files modified:** `compendium/curate/signals.py`
**Decision flagged:** strategy registry mirroring EdgeType/PageKind; `Signal` is a NamedTuple (unpack-compatible); generator bodies stay in `signals.py`.

### b — `curate run` iterates the registry

**Purpose:** Generator-agnostic runner; delete the hardcoded kind-list.

**Tasks:** build `GenerationContext`; iterate `REGISTRY` with per-generator skip (by `requires` reachability + `generate` raising); keep dedup loop + extractor step + `graph_analysis_runs` bookkeeping unchanged.

**Files modified:** `compendium/curate/run.py`
**Decision flagged:** per-generator try/except (strictly widens survival vs the old single block); extractor stays a separate non-generator step.

### c — Close-out

**Purpose:** grep gate, docs, smoke.

**Tasks:** grep gate (no hardcoded kind-list in run.py); `docs/Compendium.md` + `CONTEXT.md` notes; smoke section; `openspec validate`.

**Files modified:** `docs/Compendium.md`, `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
compendium/curate/
  signal_generator.py     # NEW — Signal + GenerationContext + SignalGenerator + REGISTRY
  signals.py              # MODIFIED — four bodies adapted to generate(ctx); re-exports Signal
  run.py                  # MODIFIED — iterate REGISTRY; no hardcoded kind-list
tests/
  test_signal_generator.py  # NEW
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | registry shape | four generators; right `kinds`/`requires`; `Signal` unpacks as 3-tuple and == plain tuple |
| 2 | unit | generate(ctx) parity | each generator returns the same signals as its old free function for a fixture context |
| 3 | integration | graph-down skip | Memgraph down → low-coverage runs; `skipped` == the three graph kinds exactly |
| 4 | integration | isolated failure | one graph generator raises → only its kinds skipped; siblings still produce |
| 5 | regression | curation suite | same signals/priorities/payloads/dedup/summary; extraction still runs as its own step |
| 6 | golden | `uv run pytest -m golden` | unaffected |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch4.1 | Same signals + summary | seed a gap, `compendium curate run` | same `by_kind` / `skipped` / `extracted_edges` as before |
| arch4.2 | Graph-down skip is kind-derived | stop Memgraph, `curate run` | `skipped` lists exactly `thin_grounding`, `dangling_concept`, `unresolved_contradiction`; low-coverage still inserted |
| arch4.3 | Extractor still separate | `curate run` with stores up | `extracted_edges` counts populated by the separate extraction step, not via a signal generator |

## Out of scope for this fix (do NOT build)

- Folding the extractor into the `SignalGenerator` protocol.
- Runtime per-kind payload validation (follow-up; the registry makes it easy).
- Changing any signal's kind, priority, or payload.
- Daemon / scheduling changes.

## Open questions to confirm before starting

1. Keep the four generator bodies in `signals.py` (referenced from the registry) — recommended, smaller diff — or move them into `signal_generator.py`? Recommendation: keep in `signals.py`.
2. Leave the extractor's skip token as the ad-hoc `"extracted_edges"` string in `skipped` (recommended; summary shape unchanged) or name it? Recommendation: leave as-is.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change complete and `openspec validate arch-signal-generator-seam` clean.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke section appended to `tests/manual/smoke_test.md`.
- [ ] Acceptance (proposal / tasks § 3.4) met: generators + kinds + store-requirements only in the registry; runner generator-agnostic; extractor separate; behaviour preserved.
- [ ] PR marked ready for review.
