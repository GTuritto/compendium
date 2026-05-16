# Tasks — phase-2-ingestion

Implements Phase 2 of `docs/COMPENDIUM_BUILD.md`. Synchronous ingestion, no job queue, no schema migration. Depends on the Phase 1 schema and `compendium/db/`.

## 1. Dependencies and ingest skeleton

- [ ] 1.1 Add runtime dependencies: `pymupdf`, `ebooklib`, `trafilatura`
- [ ] 1.2 Create the `compendium/ingest/` module layout: `adapters/`, `inspection.py`, `chunking.py`, `pipeline.py`
- [ ] 1.3 Add a content-hash utility (SHA-256 of bytes; normalized-text hash for chunks)

## 2. Source adapters

- [ ] 2.1 Define the adapter interface: parse a file/URL into extracted text, ordered sections (heading + body), and detected metadata
- [ ] 2.2 PDF adapter via `pymupdf`
- [ ] 2.3 EPUB adapter via `ebooklib`
- [ ] 2.4 Markdown adapter (passthrough; headings delimit sections)
- [ ] 2.5 HTML adapter via `trafilatura` (file or URL; boilerplate removed)
- [ ] 2.6 Adapter dispatch by file extension / URL

## 3. Inspection

- [ ] 3.1 Implement the automated checks: file integrity (parses), byte size ceiling, text yield (min tokens), encoding sanity, duplicate detection (content hash)
- [ ] 3.2 Classify `passed` / `passed_with_warnings` / `failed`; produce `inspection_notes`

## 4. Chunking

- [ ] 4.1 Structure-aware chunker: split on adapter section boundaries
- [ ] 4.2 Sliding-window fallback with overlap (sizes from `config/settings.yaml`)
- [ ] 4.3 Chunk records: `source_id`, `position`, `parent_section`, `body`, `body_hash`, approximate `token_count`

## 5. Pipeline and storage

- [ ] 5.1 Extend `compendium/db/repository.py`: insert chunks, insert `source_documents`, look up a source by `content_hash`
- [ ] 5.2 Ingestion pipeline: adapter -> inspection -> chunking -> store (`sources`, `source_documents`, `chunks`)
- [ ] 5.3 Idempotency: re-ingesting an unchanged source is a no-op; a changed source updates and replaces its chunks
- [ ] 5.4 Provenance: `--mine` sets `metadata.authored_by_me`; `--kind` sets `source_kind`

## 6. CLI

- [ ] 6.1 Add an argparse subcommand layer to `compendium/__main__.py`: no subcommand runs startup; `ingest` runs ingestion
- [ ] 6.2 `ingest <path>` accepts a file, a URL, or a directory; `--kind` and `--mine` options; reports the per-source outcome

## 7. Tests and acceptance

- [ ] 7.1 Test fixtures: small sample PDF, EPUB, Markdown, and HTML sources under `tests/fixtures/`
- [ ] 7.2 Unit tests: content hashing, chunker (structure-aware and sliding-window), inspection classification
- [ ] 7.3 Integration test: ingest the fixtures; assert `sources` rows, sane chunk counts, no duplicate chunks across re-ingestion, a failed source in `v_failed_sources`
- [ ] 7.4 **Acceptance:** ingest three sources of different formats; Postgres shows source rows and sane chunk counts with no duplicate chunks across re-ingestions; a failed inspection appears in `v_failed_sources` with a reason. `uv run pytest` passes; smoke scenarios 2.x pass
