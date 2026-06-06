## ADDED Requirements

### Requirement: A single `PageKind` registry is the home for per-kind page rules

The system SHALL provide a `PageKind` strategy registry (`compendium/wiki/page_kind.py`) carrying, per page kind, its vault `subdir`, its additional `required_fields`, its `frontmatter_fields(page)` (kind-specific frontmatter entries in contract order), its `db_fields(page)` (kind-specific values for the vault DB write), and its per-page and cross-page lint hooks. `compendium/wiki/page.py`, `lint.py`, and `vault.py` SHALL consult this registry instead of branching on `page.kind`. The `Page` dataclass SHALL remain a single flat carrier (its fields, construction, and parsing unchanged).

#### Scenario: One registry entry per kind

- **WHEN** the registry is read
- **THEN** it has exactly one record for each of `concept`, `topic`, and `source`, and `PAGE_KINDS` (the kind-name tuple) and `REQUIRED_BY_KIND` derive from it

#### Scenario: Changing a kind touches one place

- **WHEN** a kind's required fields, frontmatter shape, DB fields, subdir, or lint rule changes in its registry record
- **THEN** `page.py`, `lint.py`, and `vault.py` reflect the change with no edit to a `kind ==` conditional in any of them (none remain)

### Requirement: The refactor is byte-for-byte behaviour-preserving

Frontmatter output, rendered Markdown, lint results (rule names, severities, messages), the DB columns written, and the vault subdirectories SHALL be identical to the pre-refactor behaviour. ADR-001 (the Markdown wiki is canonical) and the frontmatter contract are unchanged.

#### Scenario: Frontmatter is byte-identical per kind

- **GIVEN** a `concept`, a `topic`, and a `source` page fixture
- **WHEN** `Page.frontmatter()` and `to_markdown()` run after the refactor
- **THEN** the emitted fields, their order, and the rendered Markdown match the pre-refactor output exactly

#### Scenario: Lint fires the same rules

- **WHEN** `lint_page` and `lint_vault` run over a vault after the refactor
- **THEN** the same rule names fire with the same severities and messages as before — the per-kind required-field check, the concept topic-id / alias rules, the topic parent + cycle rules, and the source source-id rule

#### Scenario: The vault write is unchanged

- **WHEN** `write_page` persists a page of each kind
- **THEN** the same DB columns are written with the same (UUID-coerced) values, the concept topic-links are written, and the file lands in the same `concepts/` / `topics/` / `sources/` subdir

#### Scenario: The Page carrier is untouched

- **WHEN** any existing caller constructs a `Page(...)` or reads `page.<field>` (ingest, synth, source_page, parse_markdown, repository, traces, TUI)
- **THEN** it compiles and behaves exactly as before — no construction site or attribute access changed
