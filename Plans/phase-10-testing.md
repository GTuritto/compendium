# Phase 10 — Golden dataset and testing: Implementation Plan

Date: 2026-05-26
Branch: `phase-10-testing` (off `main`)
OpenSpec change: `openspec/changes/phase-10-testing/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 10;
[docs/Compendium.md](../docs/Compendium.md) Part V (testing strategy + golden dataset).

## Goal

Regression and quality signals are automated. `uv run pytest` runs the full
suite; the golden dataset reports stable expected results on the baseline; a
deliberate ranker break trips a golden assertion; CI runs the suite on every
push and the full golden suite nightly.

## Why this plan exists

This is the final phase — the regression net. The Phase 0–9 layers
(unit/integration/pipeline/graph, 72 tests) already exist; Phase 10 adds the
golden layer and CI. The plan locks four decisions confirmed at the review gate:
(1) the golden suite is hermetic — stub embedder, asserting lexical/pipeline/
fallback/expansion stability, with real-embedding quality left to manual eval;
(2) the golden corpus reuses the existing `tests/fixtures/` plus a slug-keyed
YAML query manifest (categories A/C/D); (3) CI is GitHub Actions with the four
stores as service containers, keeping the existing skip-if-unreachable fixtures;
(4) the regression detector is a test-only ranker break, not a production toggle.

## Branch + commit strategy

- Create `phase-10-testing` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 10a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 10 complete — golden dataset and testing`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### 10a — Golden dataset, loader, seeding

**Tasks:**

1. `tests/golden/dataset.yaml`: queries over the existing fixtures with
   `id`/`category`(A/C/D)/`query`/`filters`/`expectations` (slug-keyed).
2. `tests/golden/__init__.py`: loader parsing the manifest into typed entries.
3. Seed helper: fresh `compendium_golden` DB → ingest fixtures → synth the
   expected concept(s) → `reindex all` → `graph rebuild`, all stubbed; skip if a
   store is unreachable.

**Files added:** `tests/golden/dataset.yaml`, `tests/golden/__init__.py`
**Decision flagged:** slug-keyed expectations (stable across reseeds); hermetic stub seeding.

### 10b — Golden runner + regression detector

**Tasks:**

1. `tests/test_golden.py`: run each query through `pipeline.query`; assert per
   category — A (slug in `top_k`), C (`fallback_to_chunks` + non-empty `gaps`),
   D (expansion target in ranking + `graph_expansion`, after seeding the edge).
2. Regression detector: confirm the set passes, then monkeypatch the ranker
   (disable RRF) and assert at least one expectation fails.
3. Mark golden tests `golden`; keep a small membership-only subset in the fast tier.

**Files added:** `tests/test_golden.py`
**Decision flagged:** top-K membership + flags (not exact rank); test-only break.

### 10c — Markers + CI

**Tasks:**

1. `pyproject.toml`: register `golden`/`integration` markers.
2. `.github/workflows/ci.yml` `test` job (push + PR): Postgres/OpenSearch/Qdrant/
   Memgraph service containers, `uv sync`, `COMPENDIUM_EMBED_STUB=1`, run the fast
   tier (`-m "not golden"` + golden smoke).
3. `nightly` job (schedule + `workflow_dispatch`): full golden suite + regression
   detector.

**Files added:** `.github/workflows/ci.yml`
**Files modified:** `pyproject.toml`
**Decision flagged:** service containers; existing fixtures unchanged.

### 10d — Docs, smoke, acceptance

**Tasks:**

1. Append the Phase 10 smoke section to `tests/manual/smoke_test.md`.
2. Note the golden dataset + CI in `README.md`/`CLAUDE.md` testing references.
3. Acceptance: full suite green; golden stable on baseline; ranker break trips a
   golden assertion; validate the CI YAML (`act -n` / lint).

**Files modified:** `tests/manual/smoke_test.md`, `README.md`, `CLAUDE.md`

## Final file tree after Phase 10

```text
tests/
  golden/
    __init__.py          NEW — manifest loader
    dataset.yaml         NEW — queries + expectations (A/C/D)
  test_golden.py         NEW — runner + regression detector
  manual/smoke_test.md   MOD — § Phase 10
.github/workflows/
  ci.yml                 NEW — test (push/PR) + nightly (golden) jobs
pyproject.toml           MOD — pytest markers
README.md / CLAUDE.md    MOD — testing references
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | manifest loader | well-formed entries; unknown category rejected |
| 2 | golden | Category A | expected slug in top_k for each direct query |
| 3 | golden | Category C | `fallback_to_chunks` + non-empty `gaps` |
| 4 | golden | Category D | expansion target in ranking + `graph_expansion` |
| 5 | golden | regression detector | broken ranker → ≥1 golden expectation fails |
| 6 | meta | full suite | `uv run pytest` green with stores up |
| 7 | ci | workflow valid | `ci.yml` parses; jobs/services/markers correct (`act -n`/lint) |

## Per-phase smoke test

Appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 10.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 10.1 | Full suite | `COMPENDIUM_EMBED_STUB=1 uv run pytest` | the whole suite passes (unit + integration + pipeline + graph + golden) |
| 10.2 | Golden only | `COMPENDIUM_EMBED_STUB=1 uv run pytest -m golden` | the golden suite passes on the baseline |
| 10.3 | Regression trips | run the regression-detector test | with the ranker broken, a golden assertion fails (the detector passes by catching it) |
| 10.4 | CI workflow | `act -n` (or a YAML lint) | the workflow parses; `test` and `nightly` jobs declare the four service containers |

## Out of scope for Phase 10 (do NOT build)

- The larger curated golden corpus (reference/adversarial/note sources) and query categories B (cross-source synthesis) and E (filters) — need a richer corpus and query-time filters; v0.2.
- Real-embedding semantic quality eval (manual, per Part V).
- Load/perf tests; automated TUI-rendering tests (manual smoke covers the TUI); a testcontainers refactor.
- Any schema migration or production code change.

## Open questions — resolved at the review gate (2026-05-26)

1. **Golden embedder.** RESOLVED: hermetic stub; real-embedding quality stays manual.
2. **Golden corpus.** RESOLVED: reuse the existing fixtures + a slug-keyed YAML manifest (categories A/C/D).
3. **CI.** RESOLVED: GitHub Actions with the four stores as service containers; existing skip-if-unreachable fixtures unchanged; `test` on push/PR, `nightly` for the full golden suite.
4. **Categories B and E.** RESOLVED: deferred to v0.2 (need richer corpus + filters).

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 10 met.
- [ ] PR marked ready for review.
