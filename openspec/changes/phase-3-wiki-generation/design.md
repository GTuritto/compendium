## Context

This change implements Phase 3 (wiki page generation) of `docs/COMPENDIUM_BUILD.md`. It builds on the Phase 1 schema (`wiki_pages`, `wiki_pages_topics`, `wiki_page_revisions`, `corpus_revisions`) and the Phase 2 ingestion pipeline (sources, chunks). The frontmatter contract, slug rules, content-hash rule, and lint rules are specified in `docs/Compendium.md` Part III and are implemented faithfully.

## Goals / Non-Goals

**Goals:**

- A page model that round-trips canonical Markdown + YAML frontmatter.
- Deterministic slug generation and normalized-body content hashing.
- Frontmatter lint, on every write and as `compendium lint`.
- Deterministic `source` pages; LLM-synthesized `concept`/`topic` pages.
- Vault writes with `wiki_pages` rows and `wiki_page_revisions` snapshots.

**Non-Goals:**

- Retrieval, OpenSearch, Qdrant, Memgraph (Phases 4–6).
- The curation loop and automatic synthesis (Phase 9) — Phase 3 synthesis is manually triggered.
- Graph `GROUNDS` edges — concept-page citations are recorded in the page body, not as edges, until Phase 6.

## Decisions

### Decision: `source` pages are deterministic, no LLM

A `source` page body is built by a fixed template from the `sources` row and its `chunks`: a metadata block, then the section outline (`parent_section` groups) with each section's chunk citations. No LLM call. The page is therefore free, instant, reproducible, and rebuildable from PostgreSQL. The "key claims" of a source page are its structural skeleton, not generated prose.

### Decision: `concept`/`topic` synthesis uses a real OpenAI-compatible client

Synthesis calls the endpoint configured by `SYNTHESIS_ENDPOINT`/`SYNTHESIS_MODEL` (OpenRouter or Docker Model Runner) via the `openai` SDK, which speaks the OpenAI protocol to either. Tests and offline verification use a stub synthesizer that assembles a deterministic body from the gathered chunks; the stub is selected by injection (the CLI builds the real client, tests pass the stub). Real synthesis quality is assessed manually by the curator, per the testing strategy.

### Decision: chunk gathering for synthesis is naive lexical match (pre-retrieval)

Retrieval does not exist until Phase 5. Phase 3 synthesis gathers candidate chunks with a case-insensitive `ILIKE` match of the concept title and aliases against `chunks.body`, capped at a configured limit. This is enough to ground a page across multiple sources; Phase 5 replaces it with hybrid retrieval.

### Decision: source-page generation hooks into ingestion, with a backfill command

`compendium/ingest/pipeline.py` generates the `source` page after a source is stored, so future ingests produce pages automatically. `compendium pages build` backfills `source` pages for sources ingested before this phase. A failed-inspection source still gets a `source` page (it records the failure), but a source with no chunks does not.

### Decision: a current corpus revision is ensured on first page write

The frontmatter `corpus_revision` field and `wiki_pages.corpus_revision` reference `corpus_revisions(id)`. Phase 3 ensures a current corpus-revision row exists (creating `rev-<UTC-timestamp>` if the table is empty) and stamps new pages with it. Richer corpus-revision lifecycle is deferred to Phase 7.

### Decision: lint runs before every write

The vault writer lints a page and refuses to write it if any `error`-severity rule fails; `warning`-severity rules are reported but do not block. `compendium lint` runs the same rules over the whole vault. Cross-reference rules that need PostgreSQL (`source-id-resolves`) or the vault (`topic-ids-resolve`, `no-cycle-in-topic-tree`) query those stores directly.

### Decision: concept-page citations live in the page body

A synthesized `concept` page ends with a `## Grounding` section listing each cited chunk (`chunk <uuid>` and its source title). This satisfies the acceptance ("cites at least two chunks across at least two sources") and is lintable now; the `GROUNDS` graph edges that formalize it arrive in Phase 6.

## Risks / Trade-offs

- **No LLM endpoint available during automated verification** → Phase 3 verification uses the stub synthesizer; the stub still produces a real, lint-passing body citing real gathered chunks. Real-LLM quality is the curator's manual check.
- **Naive lexical chunk gathering misses relevant chunks** → Accepted for Phase 3; it only needs to ground a page, and Phase 5 retrieval supersedes it.
- **Hooking page generation into the ingest pipeline couples the two** → Accepted; it is what "generated automatically" requires, and the backfill command keeps the operation available standalone.

## Migration Plan

No schema migration. New dependency `openai` is added to `pyproject.toml`. Generated pages are additive files under `vault/`; rolling back means removing them and their `wiki_pages`/`wiki_page_revisions` rows.

## Open Questions

- The exact synthesis prompt template will be tuned once a real endpoint is in regular use; Phase 3 ships a reasonable default.
