# Quality — Mutation Testing: Implementation Plan

> Post-v0.2 quality phase (not a numbered build phase). Standalone, in the
> `ops-backup` / `deploy` precedent. No implementation code is written until the
> user approves this plan.

Date: 2026-06-05
Branch: `quality-mutation-testing` (off `main`)
OpenSpec change: `openspec/changes/quality-mutation-testing/`
Spec source: this plan + the OpenSpec change; builds on `docs/Compendium.md` Part V
(testing strategy) and Phase 10 (golden dataset + CI).

## Goal

Add mutation testing (mutmut) as a dev-only quality layer: establish a mutation-score
baseline over a curated set of modules, kill or document the survivors on the hermetic
core, and gate the core score in scheduled CI so it cannot regress. No runtime
dependency, no schema migration, no application behavior change.

## Why this plan exists

Line coverage proves a line ran; it does not prove a test would fail if that line were
wrong. The retrieval/ingestion/curation/answer paths are Compendium's trust surface — a
weak assertion there ships a regression green. This plan locks in: the tool (mutmut), the
deterministic run contract (stub tier, covered-lines-only, golden excluded to avoid the
Qdrant HNSW flap), the two-tier target split, the mandated-shallow exclusions (ADR-004
`repository.py`, `__main__.py`, `tui/`, installer plumbing), and a score-floor gate that
is enforceable despite mutmut having no native `--fail-under`. Without it, "introduce
mutation testing" risks a slow, noisy, ungated run that nobody trusts.

## Branch + commit strategy

- Create `quality-mutation-testing` from the latest `main`. Do not commit to `main`.
- This first PR is **docs-only** (OpenSpec change + this Phase Plan), pushed as a draft
  for the review gate. No implementation code until the plan is approved.
- After approval: one commit per sub-phase (`Quality a — <sub-phase>`), green at HEAD;
  final commit `Quality complete — mutation testing`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Mark the PR ready when the testing plan and smoke test pass. The user reviews and merges.

## Sub-phases

### a — Tool + config + dry run

**Purpose:** Land a reproducible, low-noise mutmut configuration.

**Tasks:**

1. `uv add --dev mutmut`; confirm `uv run mutmut version`.
2. `[tool.mutmut]` in `pyproject.toml`: `source_paths`, `pytest_add_cli_args_test_selection = ["-m", "not golden and not live"]`, `pytest_add_cli_args = ["-p", "no:cacheprovider"]`, `mutate_only_covered_lines = true`, `do_not_mutate_patterns` (`logger\.\w+`, `log\.\w+`, `raise \w+`), `do_not_mutate` (repository.py, __main__.py, tui/*, logging.py), `also_copy` for non-source files the suite needs.
3. Dry run `mutmut run "compendium.schedule.cadence*"` with the stub env; confirm killed/survived reported, no env/fixture-induced `no tests`.

**Files added:** none (config only)
**Files modified:** `pyproject.toml`, `uv.lock`

**Decision flagged:** mutmut over cosmic-ray (simplest fit; cosmic-ray's distributed model is more than a single-user project needs). Deterministic stub tier + covered-lines-only to remove false survivors.

### b — Tier 1 baseline + survivor sweep

**Purpose:** Measure the hermetic core and close the holes it exposes.

**Tasks:**

1. `scripts/mutation.sh` (export stub env + store URLs; `core`/`stores` tier → curated module list → `mutmut run`) and `scripts/mutation_score.py` (read `mutmut results`, per-module `killed/(killed+survived)`, table, exit non-zero below a floor arg).
2. Run Tier 1 (hermetic core); record per-module baseline + wall-clock in `docs/operations/mutation-testing.md`.
3. Disposition every Tier 1 survivor: add/strengthen a unit test that kills it, or mark equivalent in `do_not_mutate` with a one-line justification; list each in the doc.
4. Re-run Tier 1; confirm the score reaches the floor with all survivors dispositioned.

**Files added:** `scripts/mutation.sh`, `scripts/mutation_score.py`, `docs/operations/mutation-testing.md`, new/strengthened tests under `tests/`
**Files modified:** `pyproject.toml` (`do_not_mutate` for equivalent mutants)

**Decision flagged:** survivors are killed or documented, never ignored. Score excludes `no tests`/`skipped`/`suspicious` so it reflects real kills.

### c — Tier 2 contract + threshold gate

**Purpose:** Extend the contract to store-touching modules and make the core gate enforceable.

**Tasks:**

1. Add the `stores` tier to `scripts/mutation.sh` (store-touching module list; needs `docker compose up` + stub env).
2. Run Tier 2 once with the stores up; record the informational baseline (score, wall-clock, notable survivors). No gate on Tier 2 yet.
3. Wire `scripts/mutation_score.py` as the Tier 1 gate (default floor from b's baseline); confirm it fails on a sub-floor result and passes on the baseline.

**Files added:** none
**Files modified:** `scripts/mutation.sh`, `docs/operations/mutation-testing.md`

**Decision flagged:** Tier 2 informational until its baseline stabilizes, then ratchet. Only Tier 1 is a hard gate at first.

### d — CI + docs + smoke + acceptance

**Purpose:** Keep the score from regressing, on a schedule.

**Tasks:**

1. `.github/workflows/mutation.yml`: `schedule:` (weekly) + `workflow_dispatch`; four service containers + stub env (mirror nightly); Tier 1 gated (hard fail), Tier 2 informational (`mutmut html`/results uploaded as an artifact). Validate the YAML (`act -n` / lint).
2. Finish `docs/operations/mutation-testing.md` (run a tier, read survivors, score formula + floor, tier/exclusion rationale, dispositions).
3. Append the mutation-testing smoke section to `tests/manual/smoke_test.md`.
4. Note mutation testing in `CLAUDE.md` / `README.md` testing references.

**Files added:** `.github/workflows/mutation.yml`
**Files modified:** `docs/operations/mutation-testing.md`, `tests/manual/smoke_test.md`, `CLAUDE.md`, `README.md`

**Decision flagged:** scheduled + on-demand only, never per-push (mutation runs are minutes-to-hours).

## Final file tree after this phase

```text
compendium/                      (unchanged — no application code change)
scripts/
  mutation.sh                    (new) tier runner: env + module list -> mutmut
  mutation_score.py              (new) result reader + score-floor gate
docs/operations/
  mutation-testing.md            (new) run guide, tiers, exclusions, dispositions
.github/workflows/
  ci.yml                         (unchanged — fast tier stays per-push)
  mutation.yml                   (new) scheduled + dispatch mutation tier
tests/
  <new/strengthened unit tests>  (new) survivor-killing assertions
  manual/smoke_test.md           (modified) mutation smoke section
pyproject.toml                   (modified) [tool.mutmut] + mutmut dev dep
uv.lock                          (modified)
CLAUDE.md / README.md            (modified) testing references
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | tooling | `mutmut run` over the core tier with the stub env | mutants generated on covered lines; killed/survived reported; no env-induced `no tests` |
| 2 | unit | Each Tier 1 survivor-killing test | the new test fails against the mutant, passes against HEAD |
| 3 | gate | `scripts/mutation_score.py` on a sub-floor and an at-floor result set | exits non-zero below the floor, zero at it |
| 4 | regression | Full fast tier after the sweep | `uv run pytest -m "not golden"` stays green |
| 5 | CI | `mutation.yml` validates and (on dispatch) runs Tier 1 gated | YAML lints; the gate fails the job below the floor |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| M.1 | Core tier runs and reports | `scripts/mutation.sh core` | mutants killed/survived printed; run completes with no backing store |
| M.2 | Score gate enforces the floor | `scripts/mutation_score.py --floor <baseline>` after a core run; then again with a lowered result | exit 0 at the floor; exit non-zero below it |
| M.3 | A survivor is visible | `mutmut results` then `mutmut show <id>` for one dispositioned mutant | the surviving diff and its status display |

## Out of scope for this phase (do NOT build)

- A repo-wide hard mutation gate — Tier 2 stays informational until it stabilizes.
- Mutating `db/repository.py` (ADR-004 raw SQL), `__main__.py`, `tui/`, or the OS-service installer plumbing.
- A per-PR mutation tier (too slow; scheduled + dispatch only).
- Chasing 100% mutation score or killing error-message/logging mutants.
- Any production behavior change or schema migration.

## Open questions to confirm before starting

1. **Tier 1 score floor.** Establish the baseline first (no hard gate), then set the floor at the achieved score rounded down and ratchet — versus a fixed target (e.g. 80%). Recommendation: floor-from-baseline.
2. **Tier 2 in CI.** Include Tier 2 in the scheduled workflow as informational from the start (so its baseline accrues), or defer Tier 2 CI entirely. Recommendation: informational from the start.
3. **Phase naming.** `quality-mutation-testing` (standalone post-v0.2) versus `v0.3-phase-1-...` (implies a v0.3 build doc). Recommendation: keep `quality-mutation-testing`.
4. **Commit trailer.** Keep the template's `Co-Authored-By: Claude Opus 4.7 (1M context)` for history consistency, or update it.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes; `uv run pytest -m "not golden"` green.
- [ ] `scripts/mutation.sh core` reaches the floor with every survivor dispositioned; the score gate fails below the floor and passes at it.
- [ ] Tier 2 informational baseline recorded.
- [ ] Scheduled `mutation.yml` validates.
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] PR marked ready for review.
