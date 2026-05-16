# BUG-001: `ingest` of a single non-existent file path crashes with a traceback

**Severity:** Low | **Priority:** P3 | **Type:** Functional / UX
**Status:** Fixed

## Environment

- **OS:** macOS 25.4.0
- **Build:** `main`, post-Phase 2 (commit `655d849`)
- **Component:** `compendium/ingest/pipeline.py`, `python -m compendium ingest`

## Description

Running `ingest` against a single file path that does not exist raises an
uncaught `FileNotFoundError`, printing a full Python traceback to the user.
A missing file inside a *directory* ingest is already caught per-file; only
the single-file path was unguarded.

## Steps to Reproduce

1. Run `uv run python -m compendium ingest /tmp/does-not-exist.md --kind note`

## Expected Behavior

A clear message that the file was not found, a non-zero exit code, and no
source row created.

## Actual Behavior

A Python traceback ending in `FileNotFoundError`. The exit code is non-zero
and no source row is created (correct), but the traceback is not an
acceptable user-facing error. Surfaced by manual test case TC-ING-009.

## Impact

- **User impact:** cosmetic; a mistyped path produces noise rather than a
  clean error. No data loss, no incorrect storage.
- **Frequency:** every single-file ingest of a non-existent path.
- **Workaround:** none needed; the command still fails safely.

## Root Cause

`pipeline.ingest()` calls `_ingest_one()` directly for a single file, and
`_ingest_one()` calls `Path(path).read_bytes()` before any error handling.
The directory branch wrapped each file in a `try/except`; the single-file
branch did not.

## Fix

`pipeline.ingest()` now checks a non-URL, non-directory path with
`Path.is_file()` and returns a `failed` `IngestResult` (`no such file: ...`)
when it is absent. A shared `_safe_ingest_one()` wrapper gives the
single-file and directory paths identical exception handling, so any other
unexpected per-source error also becomes a `failed` result rather than a
crash. Covered by regression test
`test_ingest_missing_file_is_failed_not_crash`.
