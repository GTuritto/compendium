# Manual Test Cases — Ingestion Pipeline (Phase 2)

Detailed manual test cases for the `ingestion` capability: source adapters,
inspection, chunking, idempotent storage, and the `ingest` CLI. These go
deeper than the Phase 2 smoke scenarios (`smoke_test.md` § Phase 2), covering
negative paths, boundary values, and storage integrity.

## Conventions

- Run from the repo root with the dev database up (`docker compose up -d`)
  and the schema migrated (`uv run alembic upgrade head`).
- `PSQL` below is shorthand for
  `docker compose exec -T postgres psql -U compendium -d compendium -tAc`.
- Reset to a clean corpus between independent cases with
  `uv run alembic downgrade base && uv run alembic upgrade head`.
- Settings in effect (`config/settings.yaml`): `min_text_tokens = 1000`,
  `max_source_bytes = 209715200`, `chunk.target_tokens = 512`,
  `chunk.overlap_tokens = 64`. Token estimate is ~4 characters per token.

## Test data / fixtures

Committed under `tests/fixtures/`: `sample.pdf`, `sample.epub`, `sample.md`,
`sample.html`, `broken.pdf` (deliberately invalid). Cases needing other
inputs give a creation command in their preconditions.

## Coverage matrix

| Area | Test cases |
|------|------------|
| Happy-path adapters | TC-ING-001 – 004 |
| Adapter / format negatives | TC-ING-005 – 009 |
| Inspection classification | TC-ING-010 – 014 |
| Chunking | TC-ING-015 – 018 |
| Idempotency | TC-ING-019 – 021 |
| Provenance and metadata | TC-ING-022 – 025 |
| CLI behavior | TC-ING-026 – 029 |
| Storage integrity | TC-ING-030 – 032 |

---

## Happy-path adapters

### TC-ING-001: Ingest a PDF source

**Priority:** P0 | **Type:** Functional

**Objective:** A valid PDF parses, chunks, and stores.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/sample.pdf --kind paper`
   **Expected:** Summary reports `1 source(s): 1 stored, 0 unchanged, 0 failed`; exit code 0.
2. `PSQL "SELECT kind, title, inspection_status FROM sources"`
   **Expected:** One row, `kind = paper`, `title = Sample PDF Source`, `inspection_status = passed`.
3. `PSQL "SELECT count(*) FROM chunks"`
   **Expected:** Count is greater than 0.

**Notes:** Title comes from embedded PDF metadata.

### TC-ING-002: Ingest an EPUB source

**Priority:** P0 | **Type:** Functional

**Objective:** A valid EPUB parses into per-chapter sections and stores.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/sample.epub --kind book`
   **Expected:** `1 stored`; exit 0.
2. `PSQL "SELECT title FROM sources WHERE kind = 'book'"`
   **Expected:** `Sample EPUB Source` (from EPUB DC metadata).
3. `PSQL "SELECT DISTINCT parent_section FROM chunks"`
   **Expected:** Chunks carry chapter-derived `parent_section` values.

### TC-ING-003: Ingest a Markdown source

**Priority:** P0 | **Type:** Functional

**Objective:** A Markdown file ingests; the first H1 becomes the title.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/sample.md --kind note`
   **Expected:** `1 stored`; exit 0.
2. `PSQL "SELECT title FROM sources WHERE kind = 'note'"`
   **Expected:** `Sample Markdown Source` (the first `# ` heading, not the filename).

### TC-ING-004: Ingest an HTML source

**Priority:** P0 | **Type:** Functional

**Objective:** An HTML file ingests with boilerplate removed.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/sample.html --kind web`
   **Expected:** `1 stored`; exit 0.
2. `PSQL "SELECT body FROM chunks ORDER BY position LIMIT 1"`
   **Expected:** Chunk text is the article body; the `<nav>`/`<header>`/`<footer>` boilerplate is absent.

---

## Adapter / format negatives

### TC-ING-005: Malformed PDF is recorded as failed

**Priority:** P0 | **Type:** Negative

**Objective:** An unparseable file is recorded, not crashed on.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/broken.pdf --kind paper`
   **Expected:** `1 failed`; exit code 1.
2. `PSQL "SELECT inspection_status, inspection_notes FROM sources"`
   **Expected:** `inspection_status = failed`; `inspection_notes` names the parse error.
3. `PSQL "SELECT count(*) FROM v_failed_sources"`
   **Expected:** 1.
4. `PSQL "SELECT count(*) FROM chunks"`
   **Expected:** 0 — no chunks stored for a failed source.

### TC-ING-006: Unsupported file extension

**Priority:** P1 | **Type:** Negative

**Objective:** A file format with no adapter is recorded as failed.

**Preconditions:** Clean corpus. Create `printf 'data' > /tmp/sample.xyz`.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/sample.xyz --kind article`
   **Expected:** `1 failed`; `inspection_notes` says no adapter for `.xyz`.

### TC-ING-007: Empty Markdown file

**Priority:** P1 | **Type:** Negative / Boundary

**Objective:** A zero-byte text file fails inspection rather than storing an empty source.

**Preconditions:** Clean corpus. Create `: > /tmp/empty.md`.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/empty.md --kind note`
   **Expected:** `1 failed`; `inspection_notes` is `no extractable text`.

### TC-ING-008: Empty file with a PDF extension

**Priority:** P2 | **Type:** Negative

**Objective:** A zero-byte `.pdf` fails at parse, not later.

**Preconditions:** Clean corpus. Create `: > /tmp/empty.pdf`.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/empty.pdf --kind paper`
   **Expected:** `1 failed`; `inspection_notes` names a PDF open/parse error.

### TC-ING-009: Non-existent path

**Priority:** P1 | **Type:** Negative

**Objective:** A path that does not exist is reported clearly.

**Preconditions:** None.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/does-not-exist.md --kind note`
   **Expected:** The CLI reports `1 failed` with detail `no such file: <path>`
   and exits non-zero; no source row is created.

**Notes:** Resolved by BUG-001. Before that fix this surfaced as a Python
traceback because the single-file path was not wrapped in the per-file guard
used for directory ingestion.

---

## Inspection classification

### TC-ING-010: Healthy source passes

**Priority:** P1 | **Type:** Functional

**Objective:** A source with ample text is classified `passed`.

**Preconditions:** Clean corpus. Create a Markdown file over ~4000 characters
(`> ~1000 estimated tokens`): `python -c "open('/tmp/big.md','w').write('# Big\n'+'word '*1200)"`.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/big.md --kind note`
   **Expected:** `1 stored`.
2. `PSQL "SELECT inspection_status FROM sources"`
   **Expected:** `passed`.

### TC-ING-011: Thin source warns but ingests

**Priority:** P1 | **Type:** Boundary

**Objective:** A source below the token threshold but with some text is
`passed_with_warnings` and is still stored.

**Preconditions:** Clean corpus. `sample.md` (~900 characters, well under the
~4000-character threshold) serves as the thin source.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/sample.md --kind note`
   **Expected:** `1 stored`.
2. `PSQL "SELECT inspection_status, inspection_notes FROM sources"`
   **Expected:** `passed_with_warnings`; notes mention low text yield.

### TC-ING-012: Zero-text source fails

**Priority:** P1 | **Type:** Boundary

**Objective:** A parseable source that yields no text is `failed`.

**Preconditions:** Clean corpus. Create `printf '   \n  \n' > /tmp/blank.md`.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/blank.md --kind note`
   **Expected:** `1 failed`; notes `no extractable text`.

### TC-ING-013: Encoding sanity — replacement characters

**Priority:** P2 | **Type:** Boundary

**Objective:** Heavy mojibake (replacement characters) escalates the status.

**Preconditions:** Clean corpus. Create a file decoded with errors:
`python -c "open('/tmp/bad.md','wb').write(b'# T\n'+b'\xff\xfe'*3000)"`.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/bad.md --kind note`
   **Expected:** Source is stored `passed_with_warnings` or `failed`
   depending on the replacement-character ratio (>2% warns, >10% fails);
   `inspection_notes` mentions replacement characters.

### TC-ING-014: Oversized source is rejected

**Priority:** P2 | **Type:** Boundary

**Objective:** A file over `max_source_bytes` fails the size check.

**Preconditions:** Either temporarily lower `ingestion.max_source_bytes` in
`config/settings.yaml` to a small value (e.g. 1024), or use a file larger
than 200 MB. With the lowered limit, create `/tmp/over.md` above it.

**Steps:**
1. Run `uv run python -m compendium ingest /tmp/over.md --kind note`
   **Expected:** `1 failed`; `inspection_notes` reports the byte count over
   the limit.

**Post-conditions:** Restore `max_source_bytes` if it was lowered.

---

## Chunking

### TC-ING-015: Structure-aware chunking on section boundaries

**Priority:** P1 | **Type:** Functional

**Objective:** A source with headings chunks along section boundaries.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/sample.md` (`--kind note`).
2. `PSQL "SELECT position, parent_section FROM chunks ORDER BY position"`
   **Expected:** Chunks carry the source's heading names in `parent_section`;
   positions are contiguous from 0.

### TC-ING-016: Sliding-window fallback for large unstructured text

**Priority:** P1 | **Type:** Functional

**Objective:** A large section with no sub-structure splits into overlapping
windows.

**Preconditions:** Clean corpus. Create a long single-section file:
`python -c "open('/tmp/long.md','w').write(' '.join('sentence %d here.'%i for i in range(2000)))"`.

**Steps:**
1. Ingest `/tmp/long.md` (`--kind note`).
2. `PSQL "SELECT count(*) FROM chunks"`
   **Expected:** More than one chunk; each well under the source length.
3. `PSQL "SELECT position FROM chunks ORDER BY position"`
   **Expected:** Positions are contiguous from 0.

### TC-ING-017: No duplicate chunks within a source

**Priority:** P0 | **Type:** Integrity

**Objective:** Chunk de-duplication by body hash holds.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest every fixture (`uv run python -m compendium ingest tests/fixtures/`).
2. `PSQL "SELECT count(*) FROM (SELECT source_id, body_hash FROM chunks GROUP BY source_id, body_hash HAVING count(*) > 1) d"`
   **Expected:** 0 — no two chunks of a source share a body hash.

### TC-ING-018: Chunk metadata is populated

**Priority:** P2 | **Type:** Integrity

**Objective:** Each chunk records position, body hash, and a token count.

**Preconditions:** Clean corpus; one source ingested.

**Steps:**
1. `PSQL "SELECT count(*) FROM chunks WHERE body_hash IS NULL OR token_count IS NULL"`
   **Expected:** 0.
2. `PSQL "SELECT count(*) FROM chunks WHERE token_count <= 0"`
   **Expected:** 0.

---

## Idempotency

### TC-ING-019: Re-ingesting an unchanged source is a no-op

**Priority:** P0 | **Type:** Functional

**Objective:** Same content hash produces no new rows.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/sample.pdf` (`--kind paper`).
   **Expected:** `1 stored`.
2. Note `PSQL "SELECT count(*) FROM sources"` and `... FROM chunks`.
3. Ingest the same file again.
   **Expected:** `1 unchanged`.
4. Re-check both counts.
   **Expected:** Unchanged from step 2.

### TC-ING-020: A changed source updates in place

**Priority:** P1 | **Type:** Functional

**Objective:** Re-ingesting a file whose content changed updates the existing
source and replaces its chunks rather than duplicating.

**Preconditions:** Clean corpus. Create `/tmp/note.md` with a heading and a
few paragraphs; ingest it (`--kind note`); record the `sources.id` and chunk
count.

**Steps:**
1. Edit `/tmp/note.md` (add a new section); save.
2. Ingest `/tmp/note.md` again.
   **Expected:** Summary reports `1 stored` (an update).
3. `PSQL "SELECT count(*) FROM sources"`
   **Expected:** Still 1 source; same `id` as before.
4. `PSQL "SELECT count(*) FROM source_documents"`
   **Expected:** 1 — the document row was replaced, not duplicated.

### TC-ING-021: URL re-ingestion idempotency

**Priority:** P2 | **Type:** Functional

**Objective:** Re-ingesting the same URL is a no-op.

**Preconditions:** Network access; clean corpus.

**Steps:**
1. Ingest a stable article URL: `uv run python -m compendium ingest https://example.com --kind web`.
2. Ingest the same URL again.
   **Expected:** Second run reports `1 unchanged`.

**Notes:** Known limitation — a URL source's content hash is derived from the
URL string, not the fetched page, so a *changed* page at the same URL is not
detected as changed in v0.1.

---

## Provenance and metadata

### TC-ING-022: `--mine` records authored provenance

**Priority:** P1 | **Type:** Functional

**Objective:** The `--mine` flag marks a source as authored by the user.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/sample.md --kind note --mine`
2. `PSQL "SELECT metadata->>'authored_by_me' FROM sources WHERE kind = 'note'"`
   **Expected:** `true`.

### TC-ING-023: Omitting `--mine` leaves provenance unset

**Priority:** P2 | **Type:** Functional

**Objective:** Without `--mine`, no authored flag is written.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/sample.md` (`--kind note`, no `--mine`).
2. `PSQL "SELECT metadata->>'authored_by_me' FROM sources WHERE kind = 'note'"`
   **Expected:** Empty (the key is absent).

### TC-ING-024: `--kind` sets the source kind; default applies

**Priority:** P1 | **Type:** Functional

**Objective:** `--kind` controls `sources.kind`; the default is `article`.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/sample.html` with no `--kind`.
   **Expected:** `PSQL "SELECT kind FROM sources"` returns `article`.
2. Reset; ingest the same with `--kind web`.
   **Expected:** `kind` is `web`.
3. Run `uv run python -m compendium ingest tests/fixtures/sample.md --kind bogus`
   **Expected:** argparse rejects the value; non-zero exit; choices listed.

### TC-ING-025: Detected author metadata is captured

**Priority:** P3 | **Type:** Functional

**Objective:** An author detected by an adapter is recorded.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/sample.pdf` (`--kind paper`).
2. `PSQL "SELECT metadata FROM sources"`
   **Expected:** `metadata` includes `author_detected` when the adapter
   exposed an author (`Test Author` for the fixture).

---

## CLI behavior

### TC-ING-026: Directory ingestion handles each file

**Priority:** P1 | **Type:** Functional

**Objective:** Ingesting a directory ingests every file as its own source.

**Preconditions:** Clean corpus.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/`
   **Expected:** Summary reports `5 source(s)` — one per file; the four valid
   fixtures stored, `broken.pdf` failed.
2. `PSQL "SELECT count(*) FROM sources"`
   **Expected:** 5.

### TC-ING-027: One bad file does not abort a directory ingest

**Priority:** P1 | **Type:** Negative

**Objective:** A failing file inside a directory does not stop the others.

**Preconditions:** Clean corpus. `tests/fixtures/` already contains both valid
files and `broken.pdf`.

**Steps:**
1. Run `uv run python -m compendium ingest tests/fixtures/`
   **Expected:** The summary shows both `stored` and `failed` counts; the
   valid sources are present despite `broken.pdf` failing.

### TC-ING-028: No subcommand still runs startup

**Priority:** P1 | **Type:** Regression

**Objective:** Adding the `ingest` subcommand did not break bare startup.

**Preconditions:** `.env` present.

**Steps:**
1. Run `uv run python -m compendium`
   **Expected:** Logs `Compendium starting` with resolved storage URLs;
   exit 0 (Phase 0 behavior intact).

### TC-ING-029: Exit codes reflect outcome

**Priority:** P2 | **Type:** Functional

**Objective:** A wholly-failed ingest exits non-zero; a successful one exits 0.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/broken.pdf`; check `echo $?`
   **Expected:** Non-zero (every source failed).
2. Ingest `tests/fixtures/sample.pdf`; check `echo $?`
   **Expected:** 0.

---

## Storage integrity

### TC-ING-030: A source_documents row is written

**Priority:** P1 | **Type:** Integrity

**Objective:** Ingestion records the document file with path, MIME, and size.

**Preconditions:** Clean corpus.

**Steps:**
1. Ingest `tests/fixtures/sample.pdf` (`--kind paper`).
2. `PSQL "SELECT path, mime_type, byte_size FROM source_documents"`
   **Expected:** One row; `path` is the fixture path, `mime_type` is
   `application/pdf`, `byte_size` is greater than 0.

### TC-ING-031: Chunks reference their source and cascade on delete

**Priority:** P2 | **Type:** Integrity

**Objective:** Chunk `source_id` foreign keys are valid and cascade.

**Preconditions:** Clean corpus; one source with chunks ingested.

**Steps:**
1. `PSQL "SELECT count(*) FROM chunks c LEFT JOIN sources s ON c.source_id = s.id WHERE s.id IS NULL"`
   **Expected:** 0 — every chunk references a real source.
2. `PSQL "DELETE FROM sources"` then `PSQL "SELECT count(*) FROM chunks"`
   **Expected:** 0 — chunks cascade-deleted with the source.

### TC-ING-032: Re-ingestion leaves no orphan chunks

**Priority:** P2 | **Type:** Integrity

**Objective:** Updating a changed source does not leave its old chunks behind.

**Preconditions:** Clean corpus. Ingest `/tmp/note.md`; record the chunk count.

**Steps:**
1. Change `/tmp/note.md` and re-ingest (per TC-ING-020).
2. `PSQL "SELECT count(DISTINCT source_id) FROM chunks"`
   **Expected:** 1.
3. `PSQL "SELECT count(*) FROM chunks c LEFT JOIN sources s ON c.source_id = s.id WHERE s.id IS NULL"`
   **Expected:** 0 — no chunks orphaned by the update.

---

## Execution notes

- P0 cases (001–005, 017, 019) are the smoke-critical subset; run them first.
- Cases that mutate `config/settings.yaml` (TC-ING-014) must restore it.
- Several cases overlap the automated suite (`tests/test_ingestion.py`); the
  manual cases add the boundary and negative coverage that is awkward to
  fixture in CI.
- After a full pass, reset the dev database:
  `uv run alembic downgrade base && uv run alembic upgrade head`.
