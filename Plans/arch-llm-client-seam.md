# Arch fix — Model-client seam: Implementation Plan

Date: 2026-06-07
Branch: `arch/llm-client-seam` (off `main`)
OpenSpec change: `openspec/changes/arch-llm-client-seam/`
Spec source: architecture review #3 (deep edition), candidate 3. Umbrella roadmap:
[Plans/arch-review-3-plan.md](arch-review-3-plan.md) § Phase 3.

## Goal

Consolidate the four stub-or-real model-client factories (`get_answerer`, `get_synthesizer`,
`get_extractor`, `get_embedder`) behind one `get_model_client(role)` registry, and add a single
`COMPENDIUM_LLM_STUB` offline switch — while the four protocols, their stubs, and the per-role
flags stay unchanged.

## Why this plan exists

It pins the scope (the **selection** wiring only — the adapters are deep and stay) and the one
structural decision that keeps it safe: **lazy builder thunks** so the registry module never
imports the four client classes at load time, avoiding an import cycle. It also pins that the
umbrella flag is **additive** (an OR with each role's flag), so the existing two-flag usage
across the test suite, `.env`, and the launchd smoke keeps working. Behaviour-preserving.

## Branch + commit strategy

- Create `arch/llm-client-seam` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch-LC-a — registry`, `Arch-LC-b — factories delegate`, …), green at HEAD.
- Final commit: `Arch fix complete — model-client seam`.
- Commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — The registry

**Purpose:** One home for stub-vs-real selection, with no import cycle.

**Tasks:**

1. `compendium/model_clients.py`: `ModelRole(stub_env, make_stub, make_real)`; `REGISTRY` of the four roles; lazy builder thunks (imports inside); `get_model_client(role)` (umbrella OR per-role flag → stub, else real).
2. `tests/test_model_clients.py`: per-role stub/real selection; umbrella stubs all; unknown role raises.

**Files added:** `compendium/model_clients.py`, `tests/test_model_clients.py`
**Decision flagged:** lazy thunks (no cycle); umbrella `COMPENDIUM_LLM_STUB` additive; module named `model_clients` (includes the embedder, which is not an LLM).

### b — The four factories delegate

**Purpose:** Remove the duplicated selection; callers unchanged.

**Tasks:**

1. `get_answerer` / `get_synthesizer` / `get_extractor` / `get_embedder` → one-line delegations to `get_model_client(<role>)`. Stub + real classes stay put.
2. `pipeline._embedding_model_name()` honours `COMPENDIUM_LLM_STUB` too (label stays `"stub"` under either flag).
3. Parity: same client + config per role; `answer`/`wiki`/`curate`/`index` suites green.

**Files modified:** `answer/llm.py`, `wiki/synth.py`, `curate/extract.py`, `index/embedder.py`, `retrieve/pipeline.py`
**Decision flagged:** keep the named entry points (zero caller churn).

### c — Close-out

**Purpose:** grep gate, docs, smoke.

**Tasks:** grep gate (no stub-selection outside `model_clients.py` + the label reader); `CONTEXT.md` term; smoke section; update `project-smoke-launchd-env` to the single flag; `openspec validate`.

**Files modified:** `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
compendium/
  model_clients.py        # NEW — ModelRole + REGISTRY + get_model_client
  answer/llm.py           # MODIFIED — get_answerer delegates
  wiki/synth.py           # MODIFIED — get_synthesizer delegates
  curate/extract.py       # MODIFIED — get_extractor delegates
  index/embedder.py       # MODIFIED — get_embedder delegates
  retrieve/pipeline.py    # MODIFIED — _embedding_model_name honours the umbrella flag
tests/
  test_model_clients.py   # NEW
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | per-role default | each role builds its real client from config when no flag set |
| 2 | unit | per-role stub flag | the role's own flag forces only its stub |
| 3 | unit | umbrella | `COMPENDIUM_LLM_STUB` stubs all four |
| 4 | unit | delegation parity | each `get_*()` returns what `get_model_client(role)` returns |
| 5 | regression | full fast tier + golden | unchanged behaviour, offline under the existing flags |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-lc.1 | One flag runs everything offline | `COMPENDIUM_LLM_STUB=1 compendium curate run` and `... ask "<q>"` | both run with no network/cost (all roles stubbed) |
| arch-lc.2 | Per-role flag still scoped | `COMPENDIUM_EMBED_STUB=1 compendium reindex all` (synth/answer real) | only the embedder is stubbed; the others would use real config |
| arch-lc.3 | Selection in one place | `grep -rn 'COMPENDIUM_SYNTH_STUB\|COMPENDIUM_EMBED_STUB' compendium/ \| grep -v model_clients.py` | matches only `pipeline._embedding_model_name` (the trace-label reader) |

## Out of scope for this fix (do NOT build)

- Changing the four protocols or stub bodies.
- Removing `COMPENDIUM_SYNTH_STUB` / `COMPENDIUM_EMBED_STUB`.
- Adding a new model role.

## Open questions to confirm before starting

1. `model_clients` / `get_model_client` (recommended — accurate; includes the embedder) vs the roadmap's `llm_clients` / `get_llm`? Recommendation: `model_clients`.
2. Keep the four named `get_*()` entry points (recommended) vs migrate callers? Recommendation: keep them.
3. Teach `_embedding_model_name()` the umbrella flag (recommended, one line) vs leave it? Recommendation: teach it.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] `openspec validate arch-llm-client-seam` clean.
- [ ] Testing plan passes; selection lives only in `model_clients.py`; umbrella + per-role flags both work.
- [ ] Smoke section appended; `CONTEXT.md` + launchd-env note updated.
- [ ] PR marked ready for review.
