## Why

Phase 2 fills PostgreSQL with sources and chunks, but the corpus is not yet a wiki. Phase 3 turns chunks into pages: deterministic `source` pages, LLM-synthesized `concept` and `topic` pages, all written as canonical Markdown into `vault/` with valid frontmatter and revision history. Retrieval (Phase 5) ranks these pages, so without Phase 3 there is nothing page-first to retrieve.

## What Changes

- A page model: read and write canonical Markdown with YAML frontmatter satisfying the `docs/Compendium.md` frontmatter contract for the three page kinds (`concept`, `topic`, `source`).
- Deterministic slug generation (the 7 documented rules) and the normalized-body content hash (the 5-step rule).
- Frontmatter lint: the 8 per-page and 5 cross-reference rules, run on every write and as a standalone `compendium lint` command.
- A vault writer: pages are written to `vault/{concepts,topics,sources}/`, with a `wiki_pages` row and a `wiki_page_revisions` snapshot per write.
- `source` pages — deterministic, no LLM: body built from source metadata and the source's section/chunk structure. Generated automatically when a source is ingested, with a `compendium pages build` command to backfill already-ingested sources.
- `concept` and `topic` pages — LLM synthesis via an OpenAI-compatible client (OpenRouter or Docker Model Runner, per config), triggered manually with `compendium synth`. A stub synthesizer is used in tests.

## Capabilities

### New Capabilities

- `wiki-generation`: Producing canonical wiki pages — the frontmatter contract, slug and content-hash rules, lint, deterministic `source` pages, LLM-synthesized `concept`/`topic` pages, the vault writer, and revision tracking.

### Modified Capabilities

<!-- ingestion gains a source-page generation step, but its existing
requirements are unchanged; no delta spec. -->

## Impact

- New code: `compendium/wiki/` (page model, slug, content hash, lint, source-page generation, synthesis, vault writer), CLI subcommands `lint`, `pages`, `synth`, and a source-page hook in `compendium/ingest/pipeline.py`.
- New dependency: `openai` (the OpenAI-compatible synthesis client; works against OpenRouter and Docker Model Runner).
- No schema migration: `wiki_pages`, `wiki_pages_topics`, `wiki_page_revisions`, and `corpus_revisions` already exist from Phase 1.
- New repository functions for wiki pages, revisions, topic membership, and corpus revisions.
- Pages are written into the tracked `vault/` directory.
