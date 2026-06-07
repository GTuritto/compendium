# Arch fix — ask composition seam: Implementation Plan

Date: 2026-06-07
Branch: `arch/ask-retrieval-seam` (off `main`)
OpenSpec change: `openspec/changes/arch-ask-retrieval-seam/`
Spec source: architecture review #3 (deep edition), candidate 4 (the last). Umbrella roadmap:
[Plans/arch-review-3-plan.md](arch-review-3-plan.md) § Phase 4.

## Goal

Remove `ask`'s test-only `_retrieve` parameter by extracting the DB-free composition it hides
into a public `compose_answer(question, result, …)`, leaving `ask` a single production path
(retrieve → persist → compose). Behaviour-preserving for `ask`.

## Why this plan exists

It records a **reframe of the approved candidate** that needs your sign-off: review #3 called
this a "Retrieval seam," but the faithful fix is a **composition** seam. The `_retrieve` fork
exists so the unit tests can compose over a canned result *without a database*; a `Retriever`
protocol would (a) have only one production adapter (`pipeline.run`) — a hypothetical seam by
the deepening rule — and (b) force those DB-free unit tests onto a test database. Extracting
`compose_answer` removes the fork, makes composition a real testable surface, and keeps the
unit tests fast. The e2e tests already swap retrieval via `monkeypatch(pipeline.run)`.

## Branch + commit strategy

- Create `arch/ask-retrieval-seam` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch-AR-a — compose_answer`, `Arch-AR-b — tests`, …), green at HEAD.
- Final commit: `Arch fix complete — ask composition seam`.
- Commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — Extract `compose_answer`; `ask` single-path

**Purpose:** Name the composition; delete the test-only fork.

**Tasks:**

1. `answer/compose.py`: add `compose_answer(question, result, *, answerer=None, on_token=None) -> AskResult` (rewrite → `_build_context(result, top_k)` → `_compose` → `_assemble(trace_id="", ask_trace_id="")`).
2. Remove the `_retrieve` parameter + branch from `ask`; keep only the connection block (retrieve via `pipeline.run`, persist both traces, compose). Shared helpers unchanged.
3. Update the `ask` docstring.

**Files modified:** `compendium/answer/compose.py`
**Decision flagged:** composition seam, not a `Retriever` protocol (single prod adapter; would push unit tests onto a DB).

### b — Repoint tests + verify

**Purpose:** Tests cross the real composition surface; no `_retrieve` left.

**Tasks:**

1. `tests/test_ask.py`: the three unit tests call `compose_answer(question, result, answerer=…)`; e2e tests unchanged.
2. Parity: `ask` production answer/citations/refusal + `query_traces`/`ask_traces` rows unchanged; e2e green.
3. Grep gate: no `_retrieve` in `compendium/` or `tests/`.

**Files modified:** `tests/test_ask.py`

### c — Close-out

**Purpose:** docs, smoke, validate.

**Tasks:** `CONTEXT.md` note (compose_answer DB-free; ask single-path orchestrator); smoke line; `openspec validate`.

**Files modified:** `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
compendium/answer/compose.py   # MODIFIED — + compose_answer; ask loses _retrieve
tests/test_ask.py              # MODIFIED — 3 unit tests call compose_answer
CONTEXT.md                     # MODIFIED — composed-answer note
tests/manual/smoke_test.md     # MODIFIED — arch-ar smoke line
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | compose covered | `compose_answer` over a covered result → answer + citations, empty trace ids, no DB |
| 2 | unit | compose refuse | thin result → refused, gap, suggested actions |
| 3 | integration | ask parity | covered/uncovered `ask` writes the same `query_traces` + joined `ask_traces` as before |
| 4 | grep | no fork | `grep -rn _retrieve compendium/ tests/` is empty |
| 5 | regression | fast tier + golden | unchanged |

## Per-phase smoke test

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-ar.1 | ask unchanged | `compendium ask "<covered q>"` then `ask "<uncovered q>"` | covered answers with citations + footer; uncovered refuses with gap + suggested action; both write traces |
| arch-ar.2 | no test-only seam | `grep -rn '_retrieve' compendium/ tests/` | no matches |

## Out of scope (do NOT build)

- A `Retriever` protocol / adapters (rejected — see design).
- Any change to retrieval, refusal threshold, rewrite, citations, or persistence.
- Re-retrieving inside `ask` (ADR-003).

## Open questions to confirm before starting

1. **Composition seam (`compose_answer`) vs the roadmap's literal `Retriever` protocol?**
   Recommendation: the composition seam (the `Retriever` protocol would be a single-prod-adapter
   seam and would force the DB-free unit tests onto a test DB). **The one decision to confirm.**
2. Name `compose_answer` vs `answer_over`? Recommendation: `compose_answer`.

## Definition of done

- [ ] Sub-phases committed, green at HEAD; `openspec validate` clean.
- [ ] `_retrieve` gone; `compose_answer` is the DB-free seam; `ask` single-path, production parity.
- [ ] Smoke line appended; `CONTEXT.md` updated.
- [ ] PR marked ready for review.
