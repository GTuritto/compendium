# QA Test Plan — v0.5 Curation autonomy knob (ADR-022)

Generated with `/qa-test-planner`. Tiers: **Unit** (migrated `compendium_test`
DB + stub synthesizer; skip if stores down), **Smoke** (`tests/manual/
smoke_test.md`), **Acceptance** (ADR-022). Invariants: **C1** nothing canonical
without approval unless mode=auto (auto off by default); **C2** manual is
byte-identical to pre-knob; **C3** the knob touches concept synthesis/promotion
only (ADR-010 extraction + ADR-014 contradicts unchanged); **C4** curator pages
never overwritten.

## Unit (`tests/test_curation_knob.py`)

| ID | Objective | Expected |
|----|-----------|----------|
| TC-CK-U1 | default mode | `curation_mode()` is `semi-auto` when unset |
| TC-CK-U2 | manual no-op | `autocurate(mode="manual")` drafts/promotes nothing (C2) |
| TC-CK-U3 | semi-auto drafts | drafts a `draft` concept page from an eligible signal; status stays `draft` (C1) |
| TC-CK-U4 | auto promotes | mode=auto promotes a passing draft to `canonical` |
| TC-CK-U5 | auto shadow | `shadow=True` drafts/records but promotes nothing |
| TC-CK-U6 | never overwrite | a canonical/`human` page with the target slug is skipped (C4) |
| TC-CK-U7 | scope | autocurate writes no semantic edge and no contradiction (C3) |

## Smoke (append to `tests/manual/smoke_test.md` § v0.5 Curation knob)

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.5-ck.1 | default | `compendium curate run` (mode unset) | semi-auto: drafts appear as `draft` concept pages; none canonical |
| v0.5-ck.2 | manual | set `curation.mode=manual`; `curate run` | only signals; nothing synthesized/promoted |
| v0.5-ck.3 | approve | `compendium page promote <draft-slug> --to canonical` | the drafted concept becomes canonical (curator-owned) |
| v0.5-ck.4 | auto (opt-in) | set `curation.mode=auto`; `curate run` | passing drafts promoted, marked auto-generated; off unless set |
| v0.5-ck.5 | scope | run with any mode | extraction (ADR-010) + contradicts (ADR-014) behave as before |

## Acceptance (ADR-022)

| ID | Requirement | Given/When/Then |
|----|-------------|-----------------|
| AC-CK-1 | Default semi-auto | WHEN mode unset; THEN drafts are proposed but nothing is canonical without approval (C1) |
| AC-CK-2 | Manual unchanged | WHEN mode=manual; THEN behaviour is the pre-knob slow loop (C2) |
| AC-CK-3 | Auto opt-in | WHEN mode=auto (explicit); THEN passing drafts promote, marked/reversible; off by default |
| AC-CK-4 | Guardrails | WHEN the target is a curator/canonical page; THEN it is never overwritten (C4); scope is synthesis/promotion only (C3) |

## Exit criteria

Unit green; smoke scenarios pass; AC-CK-1..4 shown; C1–C4 hold; `ci-smoke.sh` green.
