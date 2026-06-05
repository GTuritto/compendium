## Context

Phase 10 established line-covered, hermetic tests and CI. Mutation testing is the next quality layer: it measures whether the assertions are strong enough to *kill* a fault, not merely *execute* the line. This change is post-v0.2 tooling (like the deployment bundle and `ops-backup` work), not a numbered build phase; it carries the full per-phase artifacts (OpenSpec change + Phase Plan + smoke test) per the project workflow. It depends on the existing stub embedder/synth (`COMPENDIUM_EMBED_STUB`/`COMPENDIUM_SYNTH_STUB`), the marker tiers (`golden`/`integration`/`live`), and the four backing stores from `docker-compose.yml`.

The constraint that shapes every decision: **a mutant is only meaningful against a deterministic, reliably-failing test.** A test that skips when a store is down, or whose output depends on Qdrant's non-deterministic HNSW insertion order (a known v0.2 Phase 5 limitation), produces false survivors. So the design runs mutation over the deterministic stub tier with covered-lines-only filtering, and splits targets into a hermetic Tier 1 (the high-signal core) and a store-backed Tier 2.

## Goals / Non-Goals

**Goals:**

- Introduce mutmut as a dev tool with a reproducible, documented configuration.
- A per-module mutation-score baseline over the hermetic core, with survivors either killed by a new test or documented as equivalent.
- An enforceable score-floor gate, runnable locally and in scheduled CI, that prevents the core's mutation score from regressing.
- Extend the run contract to the store-touching modules (Tier 2), informational at first.

**Non-Goals:**

- A repo-wide hard gate from day one — Tier 2 is informational until its baseline stabilizes.
- Mutating mandated-shallow or wiring code: `db/repository.py` (ADR-004 raw SQL), `__main__.py`, `tui/`, OS-service installer plumbing.
- A per-PR mutation tier (mutation runs are minutes-to-hours; scheduled + on-demand only).
- 100% mutation score; perfect kill rate on error-message text or logging.
- Any production behavior change or schema migration.

## Decisions

### Decision: mutmut 3.x, configured in `pyproject.toml`

mutmut is the simplest tool that fits a single-user local project (matches the minimal-tooling ethos; cosmic-ray's SQLite-session/distributed model is more than this needs). Configuration lives in `[tool.mutmut]`:

```toml
[tool.mutmut]
source_paths = ["compendium/"]
# Deterministic tier only: stub embedder/synth, no live endpoints, no golden flap.
pytest_add_cli_args_test_selection = ["-m", "not golden and not live"]
pytest_add_cli_args = ["-p", "no:cacheprovider"]
# Only mutate lines a test actually exercises — store-skipped lines are not survivors.
mutate_only_covered_lines = true
do_not_mutate_patterns = [
    'logger\.\w+',
    'log\.\w+',
    'raise \w+',
]
do_not_mutate = [
    "compendium/__main__.py",
    "compendium/tui/*",
    "compendium/db/repository.py",
    "compendium/logging.py",
]
```

Tier targeting is by mutmut's wildcard run argument (`mutmut run "compendium.retrieve.normalize*"`), driven from `scripts/mutation.sh` so a tier is one curated module list, not a config edit.

**Alternative considered:** cosmic-ray (TOML config, explicit per-module `test-command`, operator filtering). Rejected for now: heavier ceremony for no gain at this scale; mutmut's coverage-based per-mutant test selection already narrows the reruns.

### Decision: run against the deterministic stub tier, covered-lines-only

Every mutation run sets `COMPENDIUM_EMBED_STUB=1`/`COMPENDIUM_SYNTH_STUB=1` and selects `-m "not golden and not live"`. The golden tier is excluded because the Qdrant HNSW non-determinism (v0.2 Phase 5) makes MRR-style assertions flap, which would read as survivors. `mutate_only_covered_lines = true` ensures a line only becomes a mutant if a non-skipped test touched it — so an integration test that skips because a store is down cannot manufacture a false survivor. mutmut's per-mutant coverage selection also keeps each mutant's rerun to the tests that cover it, bounding wall-clock.

**Alternative considered:** mutate everything, accept "no tests"/survivor noise. Rejected: the noise drowns the signal and erodes trust in the gate.

### Decision: two tiers, with a mandated-shallow exclusion list

- **Tier 1 — hermetic core** (no stores; the high-signal trust surface where a weak assertion is most dangerous): `retrieve/normalize.py`, `retrieve/fusion.py`, `retrieve/coverage.py`, `ingest/chunking.py`, `ingest/hashing.py`, `ingest/inspection.py`, `wiki/slug.py`, `wiki/lint.py`, `index/synonyms.py`, `schedule/cadence.py`, `answer/cost.py`, `answer/rewrite.py`, `cli/render.py`, `config.py`.
- **Tier 2 — store-touching** (needs the four stores up + stub embedder/synth): `ingest/`, `index/`, `graph/`, `retrieve/` (pipeline/search/expansion), `curate/`, `answer/compose.py` + `llm.py`, `api/`.
- **Excluded:** `db/repository.py` (raw SQL strings, mandated shallow by ADR-004 — mutmut cannot meaningfully perturb SQL text), `__main__.py` (argparse wiring), `tui/` (manual smoke owns it), `logging.py` (structlog setup), and the OS-service installers' XML/subprocess plumbing (low logic; slated for the service-unit refactor).

The split is realized as two module lists in `scripts/mutation.sh` plus the `do_not_mutate` config, not as branching test logic.

### Decision: a score-floor gate via a thin result-reader

mutmut has no native `--fail-under`. `scripts/mutation_score.py` reads the mutmut result store (`mutmut results`), computes `killed / (killed + survived)` excluding `no tests`/`skipped`/`suspicious`, prints a per-module table, and exits non-zero below a configured floor (default established from the Tier 1 baseline, not guessed). The gate runs Tier 1 in scheduled CI; Tier 2 runs informational (no gate) until its baseline settles, then ratchets.

**Alternative considered:** parse `mutmut run`'s exit code directly. Rejected: that code reflects run success, not score; an explicit reader gives a per-module breakdown and a stable gate.

### Decision: survivors are killed or documented, never ignored

For each Tier 1 survivor: either add/strengthen a unit test that asserts the behavior the mutant breaks (the preferred outcome — the survivor is a real test-suite hole), or, when the mutant is provably equivalent (no observable behavior change — e.g. a redundant boundary, a defensive branch), record it in `do_not_mutate` with a one-line justification. The disposition of every Tier 1 survivor is listed in `docs/operations/mutation-testing.md`, so the baseline is auditable.

### Decision: scheduled CI, never per-push

Mutation runs are minutes (Tier 1) to much longer (Tier 2). `.github/workflows/mutation.yml` triggers on `schedule:` (weekly) and `workflow_dispatch`, mirroring the nightly job's four service containers and stub env. The job runs Tier 1 under the score-floor gate (hard fail) and Tier 2 informational (uploaded as an artifact / `mutmut html`). Per-push CI stays the fast Phase 10 tier.

## Risks / Trade-offs

- **Mutation runs are slow; Tier 2 especially** → Tier 1 is the gated, frequently-run set; Tier 2 is scheduled + informational. Covered-lines-only and per-mutant coverage selection bound the rerun count. Wall-clock is measured and recorded in the baseline doc.
- **Equivalent mutants inflate the survivor count** → Each is dispositioned explicitly (kill or document); the score formula excludes `no tests`/`skipped` so it reflects real kills, not noise.
- **mutmut copies the project to a working dir; env/fixtures must travel** → `scripts/mutation.sh` exports the stub env and store URLs; `also_copy` carries any non-source files the suite needs (e.g. `config/`, fixtures) into the mutants dir; verified by a dry run in sub-phase a.
- **A flaky test reads as an inconsistent kill/survive** → The deterministic stub tier plus the golden exclusion removes the known flap source (Qdrant HNSW); any residual flakiness found is fixed as part of the sweep, not worked around.
- **Scope creep toward a repo-wide gate** → Explicitly deferred; Tier 2 informational until stable. The exclusion list is documented and tied to ADR-004 / the service-unit refactor.

## Migration Plan

Additive and test-only. Add the `mutmut` dev dependency, `[tool.mutmut]` config, `scripts/mutation.sh`, `scripts/mutation_score.py`, `.github/workflows/mutation.yml`, `docs/operations/mutation-testing.md`, and any survivor-killing unit tests. Rollback is deleting those files, the config block, and the dev dependency; nothing in the application, the schema, or the Phase 10 CI changes.

## Open Questions

- **Tier 1 score floor.** Recommendation: establish the baseline in sub-phase a/b with no hard gate, then set the floor at the achieved Tier 1 score rounded down (e.g. baseline 86% → floor 85%) and ratchet upward over time. Confirm the floor-from-baseline approach (versus a fixed target like 80%) at the review gate.
- **Tier 2 in CI now or later.** Recommendation: include Tier 2 in the scheduled workflow as informational (artifact only, no gate) from the start, so its baseline accrues; gate it in a later pass. Confirm versus deferring Tier 2 CI entirely.
- **Phase naming.** Filed as `quality-mutation-testing` (standalone post-v0.2 quality phase, matching the `ops-backup`/`deploy` precedent) rather than `v0.3-phase-1-...`, which would imply a v0.3 build document. Confirm the name at the review gate.
- **Commit co-author trailer.** Following the project convention in the Phase Plan template (`Co-Authored-By: Claude Opus 4.7 (1M context)`) for consistency with the existing history. Confirm if the trailer should change.
