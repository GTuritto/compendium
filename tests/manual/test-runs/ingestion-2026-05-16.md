# Test Run — Ingestion Pipeline

**Date:** 2026-05-16
**Build:** `main`, post-Phase 2 (commit `655d849`)
**Environment:** macOS 25.4.0, Python 3.12, PostgreSQL 16 (docker), dev `compendium` database
**Suite:** [ingestion_test_cases.md](../ingestion_test_cases.md) (TC-ING-001 – 032)

## Summary

| | Count |
|---|---|
| Total cases | 32 |
| Executed | 32 |
| Passed | 32 |
| Failed | 0 |
| Blocked | 0 |
| Pass rate | 100% |

## Results by priority

| Priority | Total | Pass | Fail | Blocked |
|---|---|---|---|---|
| P0 (critical) | 7 | 7 | 0 | 0 |
| P1 (high) | 15 | 15 | 0 | 0 |
| P2 (medium) | 9 | 9 | 0 | 0 |
| P3 (low) | 1 | 1 | 0 | 0 |

## Results by area

| Area | Cases | Result |
|---|---|---|
| Happy-path adapters | 001–004 | 4/4 pass |
| Adapter / format negatives | 005–009 | 5/5 pass |
| Inspection classification | 010–014 | 5/5 pass |
| Chunking | 015–018 | 4/4 pass |
| Idempotency | 019–021 | 3/3 pass |
| Provenance and metadata | 022–025 | 4/4 pass |
| CLI behavior | 026–029 | 4/4 pass |
| Storage integrity | 030–032 | 3/3 pass |

## Findings

- **BUG-001** (TC-ING-009) — a single non-existent file path crashed with a
  Python traceback. The case passed against its documented expectation
  (non-zero exit), but the run confirmed the cosmetic defect. Filed as
  [BUG-001](bug-reports/BUG-001-ingest-missing-path.md) and fixed.
- **TC-ING-004** flagged FAIL on the first automated pass — an over-broad
  check matched the word "boilerplate" inside the fixture's legitimate
  article body. Re-verified against the exact nav/header/footer strings:
  all stripped. Genuine PASS.

## Risks

None blocking. The ingestion pipeline holds under the full negative and
boundary suite.

## Next steps

- BUG-001 fixed on branch `fix-ingest-missing-path` with a regression test.
- Re-run after merge to confirm TC-ING-009 produces a clean error.
