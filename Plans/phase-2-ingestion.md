# Phase 2 — Ingestion pipeline: Implementation Plan

Date: 2026-05-16
Branch: `phase-2-ingestion` (off `main`)
OpenSpec change: `openspec/changes/phase-2-ingestion/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 2;
[docs/Compendium.md](../docs/Compendium.md) Part IV and the source inspection checklist.

## Goal

Point Compendium at a file, a URL, or a folder of notes; it parses the source,
inspects it, chunks it structure-aware, and stores it with provenance in
PostgreSQL. Re-ingesting an unchanged source is a no-op.

## Why this plan exists

It fixes the four design forks (settled in interview), the `compendium/ingest/`
module shape, the chunking approach, and the idempotency model, so the adapters,
inspection, chunker, and pipeline land in a reviewable, dependency-correct order.

## Confirmed decisions

- **Synchronous, in-process ingestion** — no job queue, no worker loop, no
  schema migration.
- **`python -m compendium ingest`** — argparse subcommands; the project stays
  non-packaged.
- **Parser libraries** — `pymupdf` (PDF), `ebooklib` (EPUB), `trafilatura`
  (HTML), Markdown passthrough.
- **Approximate token counts** — character-based estimate, no tokenizer
  dependency.
- **Provenance** — `authored_by_me` in `sources.metadata` JSONB; `--mine` flag;
  `--kind` option. No schema change.

## Prerequisite

`docker compose up -d` for the dev Postgres.

## Branch + commit strategy

- Branch `phase-2-ingestion` off `main` (done).
- One commit per sub-phase (2a–2g), each green at HEAD.
- First commit is this plan; draft PR `Phase 2 — Ingestion pipeline` after it.
- Final commit: `Phase 2 complete — ingestion pipeline`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- User reviews and merges.

## Sub-phases

### 2a — Dependencies and ingest skeleton

**Purpose:** Add the parser libraries and the module layout.

**Tasks:**

1. `uv add pymupdf ebooklib trafilatura`.
2. Create `compendium/ingest/`: `adapters/` (package), `inspection.py`,
   `chunking.py`, `pipeline.py`.
3. `compendium/ingest/hashing.py`: SHA-256 of document bytes; normalized-text
   hash for chunk bodies.

**Files added:** `compendium/ingest/{__init__,inspection,chunking,pipeline,hashing}.py`,
`compendium/ingest/adapters/__init__.py`.
**Files modified:** `pyproject.toml`, `uv.lock`.

### 2b — Source adapters

**Purpose:** Parse the four formats behind one interface.

**Tasks:**

1. Adapter interface: `parse(path_or_url) -> ParsedSource` with `text`,
   `sections` (ordered heading + body), and `metadata`.
2. `adapters/pdf.py` (pymupdf), `adapters/epub.py` (ebooklib),
   `adapters/markdown.py` (passthrough), `adapters/html.py` (trafilatura).
3. Dispatch by file extension / URL scheme.

**Files added:** `compendium/ingest/adapters/{base,pdf,epub,markdown,html,dispatch}.py`.

**Decision flagged:** adapters return structure; they do not chunk. Chunking
(2d) is format-agnostic and consumes `sections`.

### 2c — Inspection

**Purpose:** Classify each source before storage.

**Tasks:**

1. Automated checks: file integrity, byte-size ceiling, text yield (min
   tokens), encoding sanity, duplicate detection — thresholds from
   `config/settings.yaml` (`ingestion.*`).
2. Return `passed` / `passed_with_warnings` / `failed` plus `inspection_notes`.

**Files added:** content in `compendium/ingest/inspection.py`.

### 2d — Chunking

**Purpose:** Structure-aware chunking with a sliding-window fallback.

**Tasks:**

1. Structure-aware: one or more chunks per adapter section, tagged with
   `parent_section`.
2. Sliding-window fallback (target and overlap from settings) for sections
   too large or sources with no structure.
3. Each chunk: `position`, `parent_section`, `body`, `body_hash`, approximate
   `token_count`.

**Files added:** content in `compendium/ingest/chunking.py`.

### 2e — Pipeline and storage

**Purpose:** Orchestrate adapter -> inspect -> chunk -> store, idempotently.

**Tasks:**

1. Extend `compendium/db/repository.py`: `insert_chunks`,
   `insert_source_document`, `get_source_by_content_hash`, `delete_chunks`.
2. `pipeline.py`: run the stages; write `sources`, `source_documents`,
   `chunks` in one transaction.
3. Idempotency: unchanged content hash -> no-op; changed -> update the source
   row and replace its chunks. `--mine` -> `metadata.authored_by_me`;
   `--kind` -> `source_kind`.

**Files added:** content in `compendium/ingest/pipeline.py`.
**Files modified:** `compendium/db/repository.py`.

### 2f — CLI

**Purpose:** The `ingest` subcommand.

**Tasks:**

1. Argparse subcommand layer in `compendium/__main__.py`: no subcommand keeps
   the Phase 0 startup behavior; `ingest` runs ingestion.
2. `ingest <path>` accepts a file, URL, or directory; `--kind` (a `source_kind`
   value) and `--mine` flag; prints the per-source outcome.

**Files modified:** `compendium/__main__.py`.

### 2g — Tests and acceptance

**Purpose:** Lock behavior; verify acceptance.

**Tasks:**

1. `tests/fixtures/`: a small PDF, EPUB, Markdown, and HTML source, plus one
   deliberately broken source.
2. Unit tests: hashing, chunker (structure-aware and sliding-window),
   inspection classification.
3. `tests/test_ingestion.py` (integration, `compendium_test` DB): ingest the
   fixtures, assert source rows, sane chunk counts, no duplicate chunks across
   re-ingestion, the broken source in `v_failed_sources`.
4. Append the Phase 2 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/fixtures/*`, `tests/test_ingestion.py`.
**Files modified:** `tests/manual/smoke_test.md`.

## Final file tree after Phase 2

```text
compendium/ingest/
  __init__.py
  hashing.py            new
  inspection.py         new
  chunking.py           new
  pipeline.py           new
  adapters/
    __init__.py
    base.py             new
    dispatch.py         new
    pdf.py epub.py markdown.py html.py   new
compendium/db/repository.py   modified (chunks, documents, lookups)
compendium/__main__.py        modified (argparse subcommands)
tests/
  fixtures/             new (sample sources)
  test_ingestion.py     new
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | Content hashing | Same bytes -> same hash; changed bytes -> different. |
| 2 | unit | Structure-aware chunking | Sectioned source chunks on section boundaries; `parent_section` set. |
| 3 | unit | Sliding window | Structureless text splits into overlapping windows of the target size. |
| 4 | unit | Inspection | Healthy -> passed; thin -> passed_with_warnings; unparseable -> failed. |
| 5 | integration | Ingest fixtures | Source rows present, chunk counts sane, no duplicate chunks. |
| 6 | integration | Idempotency | Re-ingesting an unchanged source adds no rows. |
| 7 | integration | Failed source | A broken source appears in `v_failed_sources` with a reason. |

`uv run pytest` runs the suite; DB-backed tests use the `compendium_test`
database and skip when Postgres is unreachable.

## Per-phase smoke test (to append to tests/manual/smoke_test.md)

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 2.1 | Ingest a PDF | `uv run python -m compendium ingest tests/fixtures/sample.pdf --kind paper` | Reports success; one `sources` row, one or more `chunks`. |
| 2.2 | Ingest other formats | Ingest the EPUB, Markdown, and HTML fixtures | Three more sources; chunk counts sane for each. |
| 2.3 | Re-ingest is idempotent | Ingest `sample.pdf` again | Reports no-op; `sources` and `chunks` counts unchanged. |
| 2.4 | Failed source | Ingest the broken fixture | `inspection_status = failed`; the source is listed by `v_failed_sources` with a reason. |
| 2.5 | Authored provenance | `... ingest notes/today.md --kind note --mine` | `sources.metadata` has `authored_by_me: true`. |
| 2.6 | Directory ingest | `uv run python -m compendium ingest tests/fixtures/` | Each file in the directory becomes its own source. |

## Out of scope for Phase 2 (do NOT build)

- A job queue, worker loop, or async ingestion.
- OCR, DRM removal, or repairing broken sources.
- Wiki page generation (Phase 3) and indexing (Phase 4).
- A `compendium` console script (stays `python -m compendium`).
- Manifest-driven or recursive-glob folder ingestion.

## Open questions to confirm before starting

None. The four design forks were resolved in interview; remaining choices
(token-count heuristic, provenance via metadata) are recorded as decisions in
the OpenSpec design.

## Definition of done for Phase 2

- [ ] Sub-phases 2a–2g committed, green at HEAD.
- [ ] OpenSpec change `phase-2-ingestion` tasks checked off.
- [ ] `uv run pytest` passes.
- [ ] Smoke scenarios 2.1–2.6 pass.
- [ ] Acceptance: three sources of different formats ingest; no duplicate
      chunks across re-ingestion; a failed source shows in `v_failed_sources`.
- [ ] Draft PR `Phase 2 — Ingestion pipeline` marked ready for review.
