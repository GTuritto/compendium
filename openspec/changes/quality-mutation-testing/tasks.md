# Tasks — quality-mutation-testing

Introduces mutation testing (mutmut) as a post-v0.2 quality phase. No schema
migration; no runtime dependency (mutmut is dev-only). Task groups map to the
sub-phases (one commit per group, green at HEAD). Implementation begins only
after the Phase Plan is approved.

## 1. Tool + config + dry run (a)

- [ ] 1.1 `uv add --dev mutmut`; confirm it resolves and `uv run mutmut version` works
- [ ] 1.2 `[tool.mutmut]` in `pyproject.toml`: `source_paths = ["compendium/"]`, `pytest_add_cli_args_test_selection = ["-m", "not golden and not live"]`, `pytest_add_cli_args = ["-p", "no:cacheprovider"]`, `mutate_only_covered_lines = true`, `do_not_mutate_patterns` (`logger\.\w+`, `log\.\w+`, `raise \w+`), `do_not_mutate` (repository.py, __main__.py, tui/*, logging.py), and `also_copy` for any non-source files the suite needs
- [ ] 1.3 Dry run over one small module (`mutmut run "compendium.schedule.cadence*"`) with the stub env exported; confirm mutants are generated, tests run in the mutants dir, and killed/survived are reported (no "no tests" noise from missing fixtures/env)

## 2. Tier 1 baseline + survivor sweep (b)

- [ ] 2.1 `scripts/mutation.sh`: export the stub env (`COMPENDIUM_EMBED_STUB`/`COMPENDIUM_SYNTH_STUB`) and store URLs, take a tier name (`core`/`stores`) → a curated module list, run `mutmut run` over it; `scripts/mutation_score.py`: read `mutmut results`, compute per-module `killed/(killed+survived)`, print a table, exit non-zero below a floor arg
- [ ] 2.2 Run Tier 1 (the hermetic core list); record the per-module baseline score and wall-clock in `docs/operations/mutation-testing.md`
- [ ] 2.3 For each Tier 1 survivor: add/strengthen a unit test that kills it, OR mark it equivalent in `do_not_mutate` with a one-line justification. List every disposition in the doc
- [ ] 2.4 Re-run Tier 1; confirm the score reaches the floor with all survivors dispositioned

## 3. Tier 2 contract + threshold gate (c)

- [ ] 3.1 Extend `scripts/mutation.sh` with the `stores` tier (store-touching module list); document that it needs `docker compose up` and the stub env
- [ ] 3.2 Run Tier 2 once with the four stores up; record the informational baseline (score + wall-clock + notable survivors) in the doc. Do not gate Tier 2 yet
- [ ] 3.3 Wire `scripts/mutation_score.py` as the Tier 1 gate (default floor from the 2.2 baseline); confirm it fails when fed a sub-floor result and passes on the achieved baseline

## 4. CI + docs + smoke + acceptance (d)

- [ ] 4.1 `.github/workflows/mutation.yml`: `schedule:` (weekly) + `workflow_dispatch`; four service containers + stub env (mirror the nightly job); run Tier 1 under the score gate (hard fail) and Tier 2 informational (upload `mutmut html` / results as an artifact). Validate the YAML (`act -n` or a linter) since hosted runners are not exercised locally
- [ ] 4.2 `docs/operations/mutation-testing.md`: how to run a tier locally, read survivors (`mutmut results`/`show`/`html`), the score formula and floor, the tier/exclusion lists with rationale (ADR-004 for repository.py), and the survivor dispositions
- [ ] 4.3 Append the mutation-testing smoke section to `tests/manual/smoke_test.md` (run Tier 1; show a killed and a survived mutant; show the score gate passing at the floor and failing below it)
- [ ] 4.4 Note mutation testing in the `CLAUDE.md` / `README.md` testing references
- [ ] 4.5 **Acceptance:** `uv run pytest -m "not golden"` stays green; `scripts/mutation.sh core` reaches the floor with every survivor dispositioned; `scripts/mutation_score.py` gates correctly (fails below floor, passes at it); the Tier 2 informational baseline is recorded; the scheduled workflow YAML validates
