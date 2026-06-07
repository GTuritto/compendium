## ADDED Requirements

### Requirement: A cached config accessor parses the behavior config once

The system SHALL provide `get_config()` returning the validated no-arg `Config`, parsing
`config/settings.yaml` and `.env` once per process, and `invalidate_config_cache()` to clear
the cache. `load_config(...)` SHALL remain the uncached primitive that accepts explicit
`settings_path` / `env_file` / `load_env` (used by tests).

#### Scenario: The parse happens once

- **WHEN** `get_config()` is called more than once in a process
- **THEN** the settings file is parsed only on the first call, and subsequent calls return the cached `Config`

#### Scenario: Invalidation forces a re-read

- **WHEN** `invalidate_config_cache()` is called and then `get_config()` is called again
- **THEN** the settings file is re-read and re-validated

### Requirement: Per-section readers own each behavior section's keys and defaults

The system SHALL provide per-section readers (`retrieval`, `expansion`, `ask`, `curation`,
`extract`, `ingestion`) that each own that section's keys and defaults in one place over the
cached config. The former inline extractors SHALL delegate to them. The readers SHALL return
the same values the inline extractors returned for the same `settings.yaml`.

#### Scenario: Section contract lives in one place

- **WHEN** a behavior-config key's default needs to change
- **THEN** it changes in exactly one section reader, and every consumer of that section sees it

#### Scenario: Behaviour is preserved

- **GIVEN** the default `config/settings.yaml`
- **WHEN** retrieval, ask, curation, extraction, and ingestion run
- **THEN** they resolve the same parameter values as before the change

### Requirement: Storage URLs, vault path, and secrets stay env-sensitive

The cache SHALL cover the behavior config only. Storage-URL resolution, the LLM client
endpoint/key reads, and `vault_path` SHALL continue to read through uncached `load_config()`
so a changed environment variable takes effect on the next call.

#### Scenario: A monkeypatched storage URL is honoured

- **GIVEN** `POSTGRES_URL` (or `VAULT_PATH`) is changed in the environment
- **WHEN** a connection is opened (or an ingest resolves the vault path) afterward
- **THEN** the new value is used — these reads are not served from the behavior-config cache

### Requirement: The access surface is not pinned to stale settings

`compendium serve` SHALL invalidate the config cache so a `config/settings.yaml` change is
reflected without restarting the process. The short-lived CLI path needs no invalidation.

#### Scenario: serve reflects a settings change

- **GIVEN** `compendium serve` is running and a behavior value in `settings.yaml` is changed
- **WHEN** a subsequent request is served
- **THEN** the new value is in effect without a restart
