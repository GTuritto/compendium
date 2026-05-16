# Tasks — phase-3-wiki-generation

Implements Phase 3 of `docs/COMPENDIUM_BUILD.md`. No schema migration: the
`wiki_pages`, `wiki_pages_topics`, `wiki_page_revisions`, and
`corpus_revisions` tables exist from Phase 1.

## 1. Page model

- [ ] 1.1 `compendium/wiki/page.py`: a `Page` model and the field contract per kind (`concept`, `topic`, `source`)
- [ ] 1.2 Frontmatter (de)serialization: read and write Markdown with a YAML frontmatter block
- [ ] 1.3 `compendium/wiki/slug.py`: deterministic slug generation (the 7 rules), with collision suffixing
- [ ] 1.4 Normalized-body content hash (the 5-step rule)

## 2. Lint

- [ ] 2.1 `compendium/wiki/lint.py`: the 8 per-page rules (required fields, types, slug, id, content hash, kind-specific fields, aliases, non-empty body)
- [ ] 2.2 The 5 cross-reference rules (topic-ids-resolve, parent-topic-resolves, source-id-resolves, no-cycle-in-topic-tree, alias-uniqueness)
- [ ] 2.3 `compendium lint` CLI subcommand: run the rules over the whole vault, report errors and warnings

## 3. Vault writer and revisions

- [ ] 3.1 Extend `compendium/db/repository.py`: insert/update `wiki_pages`, insert `wiki_page_revisions`, set `current_revision_id`, `wiki_pages_topics` membership, `get_wiki_page_by_slug`, ensure a current `corpus_revisions` row
- [ ] 3.2 `compendium/wiki/vault.py`: write a `Page` to `vault/{concepts,topics,sources}/`, lint before write (block on errors), insert the `wiki_pages` row and a `wiki_page_revisions` snapshot

## 4. Source pages

- [ ] 4.1 `compendium/wiki/source_page.py`: build a deterministic `source` page body from the `sources` row and its chunks (metadata block + section outline with chunk citations)
- [ ] 4.2 Hook source-page generation into `compendium/ingest/pipeline.py` (generated after a source is stored)
- [ ] 4.3 `compendium pages build` CLI subcommand: backfill `source` pages for sources that lack one

## 5. Synthesis

- [ ] 5.1 `compendium/wiki/synth.py`: an OpenAI-compatible synthesis client (from `SYNTHESIS_ENDPOINT`/`SYNTHESIS_MODEL`) and an injectable stub synthesizer
- [ ] 5.2 Chunk gathering: case-insensitive `ILIKE` match of the concept title and aliases against `chunks.body`, capped
- [ ] 5.3 Concept/topic synthesis: gather chunks, prompt the LLM, produce a page body with a `## Grounding` section citing chunks
- [ ] 5.4 `compendium synth concept "<name>"` and `compendium synth topic "<name>"` CLI subcommands

## 6. Tests and acceptance

- [ ] 6.1 Unit tests: slug rules, content hash (frontmatter-only change is stable), frontmatter round-trip, lint rules
- [ ] 6.2 Integration tests (`compendium_test` DB): source page generation, vault write + revision row, concept synthesis with the stub
- [ ] 6.3 Append the Phase 3 smoke section to `tests/manual/smoke_test.md`; run it
- [ ] 6.4 **Acceptance:** for three ingested sources, a `source` page is written to `vault/sources/`, passes `compendium lint`, and has a `wiki_page_revisions` row; triggering synthesis for one `concept` produces a page that lint-passes and cites at least two chunks across at least two sources. `uv run pytest` passes
