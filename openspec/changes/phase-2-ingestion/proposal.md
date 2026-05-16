## Why

Phase 1 built the PostgreSQL backbone but nothing populates it. Phase 2 delivers ingestion: pointing Compendium at a file, a URL, or a folder of notes, and having it parse, inspect, chunk, and store the content with provenance. Every later phase (synthesis, indexing, retrieval) operates on the chunks and sources this phase produces, so without it the corpus is empty.

## What Changes

- Source adapters for the four supported formats: PDF (pymupdf), EPUB (ebooklib), Markdown (passthrough), HTML (trafilatura). Each yields extracted text, structural sections, and detected metadata.
- An inspection step running the automated checks from the source inspection checklist (file integrity, byte size, text yield, encoding sanity, duplicate detection), classifying each source `passed`, `passed_with_warnings`, or `failed` with notes.
- Structure-aware chunking: split on chapter/section/heading boundaries where the adapter exposes them, fall back to a sliding window with overlap. Each chunk records `source_id`, `position`, `parent_section`, a body hash, and an approximate token count.
- Idempotent storage: a source's document bytes hash into `sources.content_hash`; re-ingesting an unchanged source is a no-op; chunk `body_hash` dedupes within a source. Sources, documents, and chunks land in `sources`, `source_documents`, and `chunks`.
- Provenance for your own writing: an `--mine` flag records `authored_by_me` in `sources.metadata`; a `--kind` option sets the source kind.
- A `python -m compendium ingest <path>` subcommand. `<path>` is a file, a URL, or a directory (each file in a directory is ingested). Ingestion runs synchronously and in-process — no job queue.

## Capabilities

### New Capabilities

- `ingestion`: Parsing sources of four formats, inspecting them, chunking them structure-aware, and storing them idempotently in PostgreSQL with provenance, driven by a CLI subcommand.

### Modified Capabilities

<!-- None. Phase 2 uses the Phase 1 schema unchanged; no migration is added. -->

## Impact

- New code: `compendium/ingest/` (adapters, inspection, chunking, pipeline), CLI subcommands in `compendium/__main__.py`, new functions in `compendium/db/repository.py` (chunks, source documents, content-hash lookup).
- New dependencies: `pymupdf`, `ebooklib`, `trafilatura` (sanctioned by the Compendium.md Phase 2 task list).
- No schema migration: synchronous ingestion needs no job queue; `authored_by_me` lives in the existing `sources.metadata` JSONB.
- New test fixtures: small sample sources of each format under `tests/fixtures/`.
