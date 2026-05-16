## ADDED Requirements

### Requirement: Source adapters

The system SHALL parse sources in four formats — PDF, EPUB, Markdown, and HTML — each producing extracted text, an ordered list of structural sections, and detected metadata.

#### Scenario: PDF is parsed

- **WHEN** a PDF file is ingested
- **THEN** its text content is extracted and its pages or sections are available as ordered structural units

#### Scenario: EPUB is parsed

- **WHEN** an EPUB file is ingested
- **THEN** its chapters are extracted as ordered sections with their headings

#### Scenario: Markdown is parsed

- **WHEN** a Markdown file is ingested
- **THEN** its content passes through and its headings delimit sections

#### Scenario: HTML is parsed with boilerplate removed

- **WHEN** an HTML file or URL is ingested
- **THEN** navigation, ads, and boilerplate are stripped and the main article text is extracted

#### Scenario: Unparseable source

- **WHEN** a file that the matching adapter cannot parse is ingested
- **THEN** ingestion records the source as `failed` with a reason, and no chunks are stored

### Requirement: Source inspection

The system SHALL inspect every source before storing it, running the automated checks (file integrity, byte size, text yield, encoding sanity, duplicate detection) and classifying the source `passed`, `passed_with_warnings`, or `failed`. The classification and its reason SHALL be written to `sources.inspection_status` and `sources.inspection_notes`.

#### Scenario: Healthy source passes

- **WHEN** a well-formed source with ample extractable text is inspected
- **THEN** its `inspection_status` is `passed`

#### Scenario: Thin source warns

- **WHEN** a source yields extractable text below the configured token threshold but above zero
- **THEN** its `inspection_status` is `passed_with_warnings` and `inspection_notes` records the low yield, and it is still ingested

#### Scenario: Failed source is visible

- **WHEN** a source fails inspection (no parseable text, or unreadable)
- **THEN** its `inspection_status` is `failed`, `inspection_notes` records the reason, and the source appears in the `v_failed_sources` view

### Requirement: Structure-aware chunking

The system SHALL chunk source text along structural boundaries (chapters, sections, headings) where the adapter exposes them, and fall back to a sliding window with overlap otherwise. Each chunk SHALL record its `source_id`, ordinal `position`, `parent_section`, body hash, and an approximate token count.

#### Scenario: Structured source chunks on boundaries

- **WHEN** a source with clear section headings is chunked
- **THEN** chunk boundaries fall on section boundaries and each chunk's `parent_section` names its section

#### Scenario: Unstructured source uses the sliding window

- **WHEN** a source without detectable structure is chunked
- **THEN** it is split into overlapping windows sized by the configured target token count

### Requirement: Idempotent storage with provenance

The system SHALL store a source's metadata in `sources`, its document file in `source_documents`, and its chunks in `chunks`, with provenance. Re-ingesting an unchanged source SHALL be a no-op; re-ingesting a changed source SHALL update it rather than duplicate it.

#### Scenario: Re-ingesting an unchanged source is a no-op

- **WHEN** a source whose content hash already exists is ingested again
- **THEN** no duplicate `sources` or `chunks` rows are created

#### Scenario: Provenance for authored sources

- **WHEN** a source is ingested with the `--mine` flag
- **THEN** `sources.metadata` records `authored_by_me` as true

#### Scenario: No duplicate chunks

- **WHEN** any source is ingested
- **THEN** no two chunks of that source share a body hash

### Requirement: Ingest command

The system SHALL provide a `python -m compendium ingest <path>` subcommand where `<path>` is a file, a URL, or a directory; a directory ingests each file it contains. The command SHALL accept a `--kind` option and a `--mine` flag.

#### Scenario: Ingest a file

- **WHEN** `python -m compendium ingest <file>` is run
- **THEN** the source is parsed, inspected, chunked, and stored, and the command reports the outcome

#### Scenario: Ingest a directory

- **WHEN** `python -m compendium ingest <directory>` is run
- **THEN** each file in the directory is ingested as its own source
