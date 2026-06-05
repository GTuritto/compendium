## Why

Phase 10 gave Compendium a golden dataset and CI: the suite runs on every push and a deliberate ranker break trips a golden assertion. That proves the *golden* tests have teeth. It says nothing about the rest of the suite. Line coverage tells us a line ran; it does not tell us a test would *fail* if that line were wrong. The retrieval, ingestion, curation, and answer paths are the trust surface of a personal knowledge base — a silently weak assertion there means a regression ships green. Mutation testing closes that gap: it perturbs the code (flip a comparison, drop a call, swap a boundary) and asks whether any test notices. A surviving mutant is a hole in the suite, named and located.

This phase introduces **mutmut** as a test-only dev tool, establishes a mutation-score baseline over a curated set of modules, kills (or documents) the survivors it finds on the hermetic core, and wires a scheduled CI tier that keeps the score from regressing. It adds no runtime dependency and changes no application behavior.

## What Changes

- **mutmut as a dev dependency** (`uv add --dev mutmut`), configured in `pyproject.toml` under `[tool.mutmut]`: `source_paths`, test selection via `pytest_add_cli_args_test_selection` (`-m "not golden and not live"`, the deterministic stub tier), `pytest_add_cli_args` (`-p no:cacheprovider`), `do_not_mutate_patterns` for `structlog`/`logger` calls and `raise` message text, and `mutate_only_covered_lines = true` so uncovered/store-skipped lines do not register as false survivors.
- **A two-tier target split.** Tier 1 (hermetic core): pure-logic modules that run with no backing stores — normalize, fusion, coverage, chunking, hashing, inspection, slug, lint, synonyms, cadence, cost, rewrite, render, config. Tier 2 (store-touching): the modules whose tests need the four stores up — ingest/index/graph/retrieve/curate/answer/api — run with `docker-compose` stores and the stub embedder/synth. Excluded by mandate: `db/repository.py` (raw SQL, no ORM, ADR-004 — its body is SQL strings mutmut cannot meaningfully perturb), `__main__.py` (CLI wiring), `tui/` (covered by manual smoke), and the OS-service installer subprocess/XML plumbing (low-logic, and slated for the service-unit refactor).
- **A baseline + survivor sweep.** Run mutmut over Tier 1, record the baseline score per module in `docs/operations/mutation-testing.md`, then for each surviving mutant either add/strengthen a unit test that kills it or mark it an equivalent mutant with a one-line justification in `do_not_mutate`.
- **A runner + score gate.** `scripts/mutation.sh` brings up the stores, sets the stub env, and runs a chosen tier; `scripts/mutation_score.py` reads the mutmut result store and exits non-zero below a configured floor (so the gate is enforceable without mutmut having a native `--fail-under`).
- **A scheduled CI tier** (`.github/workflows/mutation.yml`, `schedule:` + `workflow_dispatch`, never per-push): Tier 1 with the score floor as a hard gate; Tier 2 over the service containers, informational at first. Mirrors the existing nightly job's service-container setup.

## Capabilities

### New Capabilities

- `mutation-testing`: the mutmut configuration and tier split, the deterministic-tier run contract (stub embedder/synth, covered-lines-only), the per-module baseline and survivor disposition (kill or document), the score-floor gate, and the scheduled CI tier that enforces it.

### Modified Capabilities

<!-- None. The Phase 10 golden/CI layer is unchanged; this phase adds a mutation
layer on top. No existing capability's requirements change, and there is no
schema migration. -->

## Impact

- **New code/files:** `docs/operations/mutation-testing.md`; `scripts/mutation.sh`; `scripts/mutation_score.py`; `.github/workflows/mutation.yml`; `[tool.mutmut]` config and the `mutmut` dev dependency in `pyproject.toml`/`uv.lock`; new/strengthened unit tests under `tests/` that kill survivors.
- **No application code change** except where a survivor exposes a genuine logic gap a test cannot otherwise reach; any such change is behavior-preserving and called out in its commit.
- **No schema migration; no new runtime dependency.** mutmut is a dev tool in the `dev` group, in the same class as pytest. Stack discipline (CLAUDE.md): test-only tooling, not a runtime component.
- **Out of scope** (deferred): a repo-wide hard mutation gate (Tier 2 starts informational, ratchets later); mutating `db/repository.py`, `__main__.py`, `tui/`, and the OS-service installers; a per-PR mutation tier (too slow — scheduled only); chasing 100% mutation score (diminishing returns past the trust-surface modules).
