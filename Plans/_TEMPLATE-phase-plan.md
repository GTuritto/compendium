# Phase N — <Title>: Implementation Plan

> Template. Copy to `Plans/phase-N-<short-name>.md` at the start of a phase,
> fill every section, and submit it for the user's review. No implementation
> code is written until the user approves this plan.

Date: <YYYY-MM-DD>
Branch: `phase-N-<short-name>` (off `main`)
OpenSpec change: `openspec/changes/phase-N-<short-name>/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase N;
[docs/Compendium.md](../docs/Compendium.md) Part IV.

## Goal

<1–2 sentences. The verbatim Goal from COMPENDIUM_BUILD.md, optionally sharpened.>

## Why this plan exists

<What decisions this plan locks in. What would go wrong without it.>

## Branch + commit strategy

- Create `phase-N-<short-name>` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase Na — <sub-phase>`), each green at HEAD.
- Final commit: `Phase N complete — <short title>`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### Na — <sub-phase name>

**Purpose:** <1 sentence.>

**Tasks:**

1. <Concrete, verifiable step.>
2. <...>

**Files added:** <list>
**Files modified:** <list>

**Decision flagged:** <Any locked-in decision and its rationale, or "none".>

### Nb — <sub-phase name>

<Same structure. Repeat per sub-phase.>

## Final file tree after Phase N

```text
<ASCII tree of files that exist at phase end; mark new / modified.>
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit / integration / pipeline | <scenario> | <assertion> |

## Per-phase smoke test

The scenarios appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md)
§ Phase N on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| N.1 | <scenario> | <copy-paste-ready steps> | <exit code, output, DB/index state> |

## Out of scope for Phase N (do NOT build)

- <Explicit non-goals, referencing later phases where the work belongs.>

## Open questions to confirm before starting

1. <Design choice — options and a recommendation. The user signs off here.>

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase N met.
- [ ] PR marked ready for review.
