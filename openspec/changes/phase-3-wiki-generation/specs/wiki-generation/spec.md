## ADDED Requirements

### Requirement: Canonical page frontmatter

The system SHALL read and write wiki pages as Markdown files with YAML frontmatter satisfying the `docs/Compendium.md` frontmatter contract: the fields required for all kinds, plus the kind-specific fields for `concept`, `topic`, and `source`.

#### Scenario: Page round-trips through frontmatter

- **WHEN** a page is written to the vault and read back
- **THEN** its kind, title, slug, identity, status, generator, and kind-specific fields are unchanged

#### Scenario: Frontmatter carries the required fields

- **WHEN** any page is written
- **THEN** its frontmatter contains every field required for its kind

### Requirement: Deterministic slug generation

The system SHALL derive a page slug from its title by the documented rules: lowercase, collapse whitespace and underscores to hyphens, strip diacritics, remove characters outside `[a-z0-9-]`, trim hyphens, truncate to 80 characters at a hyphen boundary, and append `-2`, `-3`, … on collision with an existing page of the same kind.

#### Scenario: Slug is deterministic

- **WHEN** a slug is generated twice from the same title and kind
- **THEN** the two slugs are identical

#### Scenario: Colliding slug is suffixed

- **WHEN** a slug would collide with an existing page of the same kind
- **THEN** a numeric suffix is appended to make it unique

### Requirement: Content hash over the normalized body

The system SHALL compute `content_hash` as the SHA-256 of the normalized page body (frontmatter stripped, line endings normalized, trailing whitespace and surrounding blank lines removed).

#### Scenario: Frontmatter-only change does not change the hash

- **WHEN** a page's frontmatter changes but its body does not
- **THEN** the recomputed `content_hash` is unchanged

### Requirement: Frontmatter lint

The system SHALL lint pages against the per-page and cross-reference rules. `error`-severity violations SHALL block a write; `warning`-severity violations SHALL be reported only. `compendium lint` SHALL run the rules over the whole vault.

#### Scenario: Invalid page is rejected on write

- **WHEN** a page that violates an `error`-severity lint rule is written
- **THEN** the write is refused and the failing rule is reported

#### Scenario: Lint command reports vault state

- **WHEN** `compendium lint` runs over a vault of valid pages
- **THEN** it reports zero errors

### Requirement: Deterministic source pages

For each ingested source the system SHALL generate one `source` page, written to `vault/sources/`, built deterministically from the source's metadata and its chunk structure with no LLM call. Generation SHALL happen automatically on ingestion, and `compendium pages build` SHALL backfill sources that lack a page.

#### Scenario: Ingesting a source generates its page

- **WHEN** a source is ingested
- **THEN** a `source` page for it exists in `vault/sources/`, passes lint, and has a row in `wiki_page_revisions`

#### Scenario: Backfill generates missing source pages

- **WHEN** `compendium pages build` runs with sources that have no `source` page
- **THEN** a `source` page is generated for each

### Requirement: Concept and topic synthesis

The system SHALL synthesize `concept` and `topic` pages from corpus chunks using the configured OpenAI-compatible LLM endpoint, triggered manually by `compendium synth`. A synthesized `concept` page SHALL cite the chunks that ground it.

#### Scenario: Concept synthesis produces a grounded page

- **WHEN** synthesis is triggered for a concept covered by multiple sources
- **THEN** a `concept` page is written that passes lint and cites at least two chunks drawn from at least two sources

#### Scenario: Synthesis is reproducible under the test stub

- **WHEN** synthesis runs with the stub synthesizer
- **THEN** it produces a deterministic page body without contacting an LLM endpoint

### Requirement: Revision tracking

Every page write SHALL insert a `wiki_page_revisions` row capturing the full body, content hash, frontmatter, and generator, and SHALL update the `wiki_pages` row to point at the new revision.

#### Scenario: A write records a revision

- **WHEN** a page is written or rewritten
- **THEN** a new `wiki_page_revisions` row exists for it with the correct `generator`, and `wiki_pages.current_revision_id` points at that row
