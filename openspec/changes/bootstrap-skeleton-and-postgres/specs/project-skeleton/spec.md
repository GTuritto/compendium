## ADDED Requirements

### Requirement: Managed Python project

The project SHALL be a `uv`-managed Python 3.12 package named `compendium`, with dependencies declared in `pyproject.toml` and the interpreter version pinned in `.python-version`.

#### Scenario: Project installs from a clean checkout

- **WHEN** a developer runs `uv sync` on a fresh checkout
- **THEN** the `compendium` package and all declared dependencies install without error against Python 3.12

#### Scenario: Package layout exists

- **WHEN** the project is inspected
- **THEN** the directories `compendium/{ingest,wiki,index,retrieve,graph,trace,tui,db}/`, `config/`, `migrations/`, `tests/`, and `vault/` all exist

### Requirement: Configuration loading and validation

The system SHALL load non-secret behavior configuration from `config/settings.yaml` and secret/URL values from environment variables, resolving env-var references named in the YAML at startup. Validation SHALL confirm that every required value is present and parseable; it SHALL NOT open network connections to any storage backend.

#### Scenario: All required configuration present

- **WHEN** configuration is loaded with every required environment variable set
- **THEN** a validated configuration object is produced exposing the resolved storage URLs and behavior settings

#### Scenario: Required value missing

- **WHEN** configuration is loaded with a required environment variable unset
- **THEN** validation fails with an error naming the missing variable, and no partially-initialized configuration is returned

#### Scenario: Validation performs no I/O

- **WHEN** configuration is validated while all storage backends are unreachable
- **THEN** validation still succeeds, because it only resolves and parses values and never connects

### Requirement: Application entrypoint

The system SHALL provide a `python -m compendium` entrypoint that loads and validates configuration, reports startup, and exits cleanly.

#### Scenario: Successful startup

- **WHEN** `uv run python -m compendium` is executed with valid configuration
- **THEN** it prints `Compendium starting` and the resolved storage URLs, then exits with status code 0

#### Scenario: Startup with invalid configuration

- **WHEN** `uv run python -m compendium` is executed with a required variable missing
- **THEN** it prints the validation error and exits with a non-zero status code

### Requirement: Structured logging

The system SHALL emit logs as JSON to stderr using `structlog`.

#### Scenario: Log output is JSON on stderr

- **WHEN** the application logs an event during startup
- **THEN** the event is written to stderr as a single-line JSON object
