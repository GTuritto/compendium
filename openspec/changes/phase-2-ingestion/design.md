## Context

This change implements Phase 2 (ingestion pipeline) of `docs/COMPENDIUM_BUILD.md`. It builds on the Phase 1 schema (`sources`, `source_documents`, `chunks`) and the `compendium/db/` access layer. The four foundational decisions below were settled in a design interview; the rest follow `docs/Compendium.md` Part IV and the source inspection checklist.

## Goals / Non-Goals

**Goals:**

- Parse PDF, EPUB, Markdown, and HTML into text plus structural sections.
- Inspect each source and classify it, recording the reason on failure.
- Chunk structure-aware, with a sliding-window fallback.
- Store sources, documents, and chunks idempotently with provenance.
- A `python -m compendium ingest` subcommand over files, URLs, and folders.

**Non-Goals:**

- A job queue, worker loop, or asynchronous ingestion.
- OCR, DRM stripping, or fixing broken sources (recorded as failed, not repaired).
- Wiki page synthesis (Phase 3) or indexing (Phase 4).
- Real-time or streaming ingestion.

## Decisions

### Decision: Synchronous, in-process ingestion — no job queue

`docs/Compendium.md` mentions a Postgres job table with a worker loop, but for a single user ingesting a file at a time that is over-engineering. `compendium ingest` parses, inspects, chunks, and stores inline, then returns. No `ingestion_jobs` table, no migration, no worker loop. A queue can be added later if bulk ingestion ever needs retry/status tracking.

### Decision: `python -m compendium ingest` — no console script

The project stays non-packaged (the Phase 0 decision). `compendium/__main__.py` gains an argparse subcommand layer: no argument runs the existing startup, `ingest <path>` runs ingestion. This avoids adding a build backend and `[project.scripts]`. The `compendium ingest` form in the docs is shorthand for `python -m compendium ingest`.

### Decision: Parser libraries — pymupdf, ebooklib, trafilatura

PDF via `pymupdf` (strong extraction on multi-column and complex layouts; AGPL, irrelevant for a local non-distributed tool), HTML via `trafilatura` (modern, well-maintained boilerplate removal), EPUB via `ebooklib`, Markdown by passthrough. Each adapter implements a common interface returning extracted text, an ordered list of sections (heading plus body), and detected metadata.

### Decision: Approximate token counts, no tokenizer dependency

`chunks.token_count` is filled with a lightweight character-based estimate (~4 characters per token), not a real tokenizer. Chunking is structure-aware first; the sliding-window fallback only needs an approximate target size, and chunk parameters are tuned against the Phase 10 golden dataset anyway. This avoids pulling in `tiktoken` or `transformers`.

### Decision: Provenance via `sources.metadata`, no schema change

`authored_by_me` is a boolean in the existing `sources.metadata` JSONB, set by the `--mine` CLI flag. The source kind comes from a `--kind` option (one of the `source_kind` enum values). No new column and no enum change: your own notes are kind `note`, your finished pieces `article`, distinguished from external works by the `authored_by_me` flag.

### Decision: Idempotency by content hash

`sources.content_hash` is the SHA-256 of the document bytes. Re-ingesting a source whose hash already exists is a no-op. A changed source (new hash) updates the existing `sources` row and replaces its chunks. Within a source, `chunks.body_hash` (hash of normalized chunk text) backs the `UNIQUE (source_id, body_hash)` constraint and dedupes.

## Risks / Trade-offs

- **Adapter extraction quality varies by source** → Inspection's text-yield check flags thin extraction as `passed_with_warnings` or `failed`; the manual inspection checklist remains a human step.
- **Approximate token counts drift from real tokenizer counts** → Accepted; counts are advisory for chunk sizing, refined against the golden dataset in Phase 10.
- **Synchronous ingestion blocks on large files** → Acceptable at single-user, batch scale; a queue is the documented escape hatch if it ever matters.
- **`--kind` is user-supplied and can be wrong** → Accepted; the source page surfaces it (Phase 3) for correction, and re-ingestion can fix metadata.

## Migration Plan

No schema migration. New dependencies are added to `pyproject.toml`; `uv sync` installs them. Ingestion is additive; nothing to roll back beyond removing the new code.

## Open Questions

- Folder ingestion currently treats every file in a directory as a separate source; whether to support a manifest or recursive globbing is deferred until real use shows the need.
