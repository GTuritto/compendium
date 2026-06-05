## ADDED Requirements

### Requirement: Mutation testing tool and configuration

The system SHALL provide a configured mutation-testing tool (mutmut) as a dev-only dependency. The configuration SHALL live in `pyproject.toml` under `[tool.mutmut]` and SHALL select the deterministic test tier (the stub embedder/synth, excluding the `golden` and `live` markers), mutate only lines exercised by a non-skipped test, and exclude logging/raise statements and the mandated-shallow modules (`db/repository.py`, `__main__.py`, `tui/`, `logging.py`) from mutation.

#### Scenario: A configured mutation run generates and evaluates mutants

- **WHEN** `mutmut run` is invoked over a configured module with the stub environment set
- **THEN** mutants are generated only on lines a non-skipped test covers, the deterministic tier runs against each mutant, and each mutant is reported as killed or survived (no `no tests` result caused by missing environment or fixtures)

### Requirement: Deterministic mutation run contract

The mutation run SHALL be deterministic: it SHALL set the stub embedder and stub synthesizer, SHALL exclude the golden tier (whose ranking is non-deterministic across reseeds), and SHALL require no live model endpoint. A line that is only covered by a test that skips when a backing store is unreachable SHALL NOT register as a surviving mutant.

#### Scenario: A store-skipped line does not become a false survivor

- **WHEN** a mutation tier runs and a backing store is unreachable, so the covering integration test skips
- **THEN** the affected line is not mutated (covered-lines-only), and no survivor is reported for it

### Requirement: Tiered mutation targets

The system SHALL define two mutation tiers: a hermetic core tier (modules that run with no backing stores) and a store-touching tier (modules whose tests require the backing stores and the stub embedder/synth). A runner SHALL select a tier by name and run mutmut over that tier's module list.

#### Scenario: The core tier runs without backing stores

- **WHEN** the runner is invoked for the hermetic core tier
- **THEN** mutmut runs over the core module list and completes without any backing store available

#### Scenario: The store tier runs against the backing stores

- **WHEN** the runner is invoked for the store-touching tier with the four stores up and the stub environment set
- **THEN** mutmut runs over the store-touching module list using the deterministic stub tier

### Requirement: Mutation-score gate

The system SHALL compute a mutation score per module as `killed / (killed + survived)`, excluding `no tests`, `skipped`, and `suspicious` outcomes, and SHALL provide a gate that exits non-zero when the score falls below a configured floor. The floor SHALL be derived from the established hermetic-core baseline.

#### Scenario: The gate fails below the floor

- **WHEN** the score reader evaluates a result set whose core mutation score is below the configured floor
- **THEN** it prints the per-module breakdown and exits non-zero

#### Scenario: The gate passes at the baseline

- **WHEN** the score reader evaluates a result set at or above the floor
- **THEN** it prints the per-module breakdown and exits zero

### Requirement: Survivor disposition

Every surviving mutant in the hermetic core tier SHALL be dispositioned: either a test SHALL be added or strengthened to kill it, or it SHALL be recorded as an equivalent mutant in the exclusion configuration with a written justification. The disposition of each core survivor SHALL be documented.

#### Scenario: A surviving mutant is killed by a new assertion

- **WHEN** a core mutant survives the baseline run
- **THEN** a test is added or strengthened so the mutant is killed on re-run, or the mutant is recorded as equivalent with a justification, and the disposition is listed in the operations doc

### Requirement: Scheduled mutation CI tier

CI SHALL run mutation testing on a schedule (and on manual dispatch), never on every push. The scheduled job SHALL provide the four backing stores as service containers and the stub environment, SHALL run the hermetic core tier under the score-floor gate as a hard failure, and SHALL run the store-touching tier informationally.

#### Scenario: The scheduled job gates the core tier

- **WHEN** the scheduled mutation workflow runs
- **THEN** the hermetic core tier runs under the score gate and the job fails if the core score is below the floor, while the store-touching tier runs informationally

#### Scenario: Mutation testing does not run per push

- **WHEN** a commit is pushed or a pull request is opened
- **THEN** the per-push CI runs the existing fast tier only, and the mutation workflow does not run
