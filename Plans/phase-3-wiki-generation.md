# Phase 3 — Wiki page generation: Implementation Plan

Date: 2026-05-16
Branch: `phase-3-wiki-generation` (off `main`)
OpenSpec change: `openspec/changes/phase-3-wiki-generation/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 3;
[docs/Compendium.md](../docs/Compendium.md) Part III (canonical page frontmatter).

## Goal

Turn ingested chunks into canonical wiki pages: deterministic `source` pages
and LLM-synthesized `concept`/`topic` pages, written to `vault/` with valid
frontmatter, linted, and revisioned in PostgreSQL.

## Why this plan exists

It fixes the page model, the writer/lint ordering, the synthesis client
shape, and the source-page generation trigger before any of it is built, so
the frontmatter contract, lint, source pages, and synthesis land in a
reviewable, dependency-correct order.

## Confirmed decisions

- **`source` pages — deterministic, no LLM.** Body built by a fixed template
  from the `sources` row and its chunk structure.
- **`concept`/`topic` synthesis — real OpenAI-compatible client** (`openai`
  SDK against `SYNTHESIS_ENDPOINT`). Tests and offline verification use an
  injectable stub synthesizer.
- **Source-page generation hooks into `ingest`**, with `compendium pages
  build` to backfill already-ingested sources.
- Chunk gathering for synthesis is naive `ILIKE` matching (pre-retrieval);
  Phase 5 replaces it. A current `corpus_revisions` row is ensured on first
  write. No schema migration.

## Prerequisite

`docker compose up -d` for the dev Postgres.

## Branch + commit strategy

- Branch `phase-3-wiki-generation` off `main` (done).
- One commit per sub-phase (3a–3f), each green at HEAD.
- First commit is this plan; draft PR `Phase 3 — Wiki page generation` after it.
- Final commit: `Phase 3 complete — wiki page generation`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- User reviews and merges.

## Sub-phases

### 3a — Page model: frontmatter, slug, content hash

**Purpose:** Read and write canonical pages; deterministic slug and hash.

**Tasks:**

1. `compendium/wiki/page.py`: a `Page` model; the field contract per kind;
   Markdown + YAML frontmatter (de)serialization.
2. `compendium/wiki/slug.py`: `slugify(title, existing)` — the 7 rules with
   collision suffixing.
3. Normalized-body `content_hash` (the 5-step rule) in `compendium/wiki/page.py`.

**Files added:** `compendium/wiki/{__init__,page,slug}.py`.

### 3b — Lint

**Purpose:** Validate pages; the `compendium lint` command.

**Tasks:**

1. `compendium/wiki/lint.py`: the 8 per-page rules.
2. The 5 cross-reference rules (PostgreSQL- and vault-backed).
3. `compendium lint` CLI subcommand: run over the vault, report errors/warnings.

**Files added:** `compendium/wiki/lint.py`.
**Files modified:** `compendium/__main__.py`.

### 3c — Vault writer and revisions

**Purpose:** Persist pages to disk and to PostgreSQL.

**Tasks:**

1. Extend `compendium/db/repository.py`: insert/update `wiki_pages`, insert
   `wiki_page_revisions`, set `current_revision_id`, `wiki_pages_topics`
   membership, `get_wiki_page_by_slug`, ensure a current `corpus_revisions` row.
2. `compendium/wiki/vault.py`: write a `Page` to `vault/{concepts,topics,sources}/`,
   lint before write (block on `error`-severity), insert the `wiki_pages` row
   and a `wiki_page_revisions` snapshot.

**Files added:** `compendium/wiki/vault.py`.
**Files modified:** `compendium/db/repository.py`.

### 3d — Source pages

**Purpose:** Deterministic `source` pages, generated on ingest.

**Tasks:**

1. `compendium/wiki/source_page.py`: build a `source` page body from the
   `sources` row and its chunks (metadata block + section outline with chunk
   citations).
2. Hook generation into `compendium/ingest/pipeline.py` after a source stores.
3. `compendium pages build` CLI subcommand: backfill `source` pages.

**Files added:** `compendium/wiki/source_page.py`.
**Files modified:** `compendium/ingest/pipeline.py`, `compendium/__main__.py`.

### 3e — Synthesis

**Purpose:** LLM-synthesized `concept`/`topic` pages.

**Tasks:**

1. `compendium/wiki/synth.py`: an OpenAI-compatible synthesis client and an
   injectable stub synthesizer.
2. Chunk gathering: `ILIKE` match of title and aliases against `chunks.body`,
   capped by config.
3. Concept/topic synthesis: gather chunks, prompt, produce a body with a
   `## Grounding` section citing chunks.
4. `compendium synth concept "<name>"` / `synth topic "<name>"` subcommands.

**Files added:** `compendium/wiki/synth.py`.
**Files modified:** `compendium/__main__.py`, `pyproject.toml` (`openai`).

### 3f — Tests and acceptance

**Purpose:** Lock behavior; verify acceptance.

**Tasks:**

1. Unit tests: slug rules, content hash, frontmatter round-trip, lint rules.
2. Integration tests (`compendium_test` DB): source page generation, vault
   write + revision, concept synthesis with the stub.
3. Append the Phase 3 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/test_wiki.py`.
**Files modified:** `tests/manual/smoke_test.md`.

## Final file tree after Phase 3

```text
compendium/wiki/
  __init__.py
  page.py          new  (Page model, frontmatter, content hash)
  slug.py          new
  lint.py          new
  vault.py         new  (writer + revisions)
  source_page.py   new
  synth.py         new  (LLM client + stub)
compendium/db/repository.py    modified (wiki pages, revisions, corpus rev)
compendium/ingest/pipeline.py  modified (source-page hook)
compendium/__main__.py         modified (lint, pages, synth subcommands)
tests/test_wiki.py             new
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | Slug rules | Diacritics, collapsing, truncation, collision suffix. |
| 2 | unit | Content hash | A frontmatter-only change leaves the hash stable. |
| 3 | unit | Frontmatter round-trip | A page written and read back is unchanged. |
| 4 | unit | Lint | Each error rule rejects a violating page; valid pages pass. |
| 5 | integration | Source page | Ingesting a source writes a lint-passing `source` page + revision. |
| 6 | integration | Vault write | A write inserts a `wiki_pages` row and a `wiki_page_revisions` snapshot. |
| 7 | integration | Synthesis (stub) | Stub synthesis produces a lint-passing `concept` page citing >=2 chunks across >=2 sources. |

`uv run pytest`; DB-backed tests use `compendium_test` and skip without Postgres.

## Per-phase smoke test (to append to tests/manual/smoke_test.md)

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 3.1 | Source page on ingest | `uv run python -m compendium ingest tests/fixtures/sample.pdf --kind paper` | A `source` page appears in `vault/sources/`. |
| 3.2 | Backfill source pages | Ingest the other fixtures, then `uv run python -m compendium pages build` | A `source` page exists for every ingested source. |
| 3.3 | Lint a clean vault | `uv run python -m compendium lint` | Reports zero errors. |
| 3.4 | Lint catches a bad page | Hand-edit a page to break a required field; `uv run python -m compendium lint` | The failing rule is reported as an error. |
| 3.5 | Concept synthesis | `COMPENDIUM_SYNTH_STUB=1 uv run python -m compendium synth concept "psychological safety"` | A `concept` page is written, passes lint, and its `## Grounding` cites >=2 chunks across >=2 sources. |
| 3.6 | Revision recorded | After 3.5, `PSQL "SELECT generator FROM wiki_page_revisions"` | A revision row exists with the expected generator. |

## Out of scope for Phase 3 (do NOT build)

- Retrieval, OpenSearch, Qdrant, Memgraph (Phases 4–6).
- The curation loop / automatic synthesis (Phase 9).
- `GROUNDS` graph edges — citations live in the page body for now.
- Tuning the synthesis prompt against real output (a reasonable default ships).

## Open questions to confirm before starting

None. The three design forks were resolved in interview; remaining choices
are recorded as decisions in the OpenSpec design.

## Verification note

Automated verification and the smoke walk use the **stub synthesizer** — no
live LLM endpoint is assumed. The stub assembles a real, lint-passing page
body from real gathered chunks, so the structural acceptance (lint-passes,
cites >=2 chunks across >=2 sources) is genuinely exercised. Real-LLM
synthesis quality is the curator's manual check once an endpoint is configured.

## Definition of done for Phase 3

- [ ] Sub-phases 3a–3f committed, green at HEAD.
- [ ] OpenSpec change `phase-3-wiki-generation` tasks checked off.
- [ ] `uv run pytest` passes.
- [ ] Smoke scenarios 3.1–3.6 pass.
- [ ] Acceptance: three ingested sources each have a lint-passing `source`
      page with a revision row; a synthesized `concept` page lint-passes and
      cites >=2 chunks across >=2 sources.
- [ ] Draft PR `Phase 3 — Wiki page generation` marked ready for review.
