# Cumulative smoke walk — 2026-05-30 (post v0.2 Phase 2 merge)

| Field | Value |
| --- | --- |
| Host | Mac mini Apple Silicon |
| OS | macOS 25.5.0 |
| Date | 2026-05-30 |
| Trigger | v0.2 Phase 2 (PR #32) merged to `main` |
| Reset | `docker compose down -v && up -d && alembic upgrade head`; vault wiped |
| `pg_dump` / `pg_restore` | 18.4 via Homebrew `libpq` |
| `rsync` | OpenBSD `openrsync` 2.6.9 compatible (macOS default) |
| Stubs (Phases 0–10, v0.2-2) | `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1` |
| Stubs (v0.2-1) | unset (real OpenRouter for both seams) |
| Smoke source | [`../smoke_test.md`](../smoke_test.md) |

**Bottom line.** Every CLI-runnable scenario from Phase 0 through
v0.2-2 passed on a freshly reset stack. Phase 8 (TUI) and 9.8 (TUI
curate) are interactive-only and stay manual.

## Phase 0 — Project skeleton (4/4)

| # | Scenario | Result |
| --- | --- | --- |
| 0.1 | Cold start | PASS (exit 0) |
| 0.2 | Missing required variable (`.env` hidden) | PASS (exit 1) |
| 0.3 | Validation does no I/O (`.env` hidden, stores at closed ports) | PASS (exit 0) |
| 0.4 | Log structure (JSON event/level/ts) | PASS |

## Phase 1 — PostgreSQL operational backbone (5/5)

| # | Scenario | Result |
| --- | --- | --- |
| 1.1 | Dev DB up | PASS |
| 1.2 | `upgrade head` builds schema | PASS (10 enums, 13 tables, 4 views) |
| 1.3 | `downgrade base` reverses cleanly | PASS |
| 1.4 | Repository round-trip via `compendium/db/` | PASS |
| 1.5 | Operational views queryable | PASS |

## Phase 2 — Ingestion (6/6)

| # | Scenario | Result |
| --- | --- | --- |
| 2.1 | Ingest PDF | PASS (1 stored, 4 chunks) |
| 2.2 | Ingest EPUB + HTML | PASS |
| 2.3 | Re-ingest idempotent | PASS (1 unchanged) |
| 2.4 | Failed source (`broken.pdf`) | PASS (1 failed) |
| 2.5 | Authored provenance (`--mine`) | PASS |
| 2.6 | Directory ingest (all unchanged) | PASS (5 unchanged) |

Post-Phase-2 state: 5 sources, 14 chunks.

## Phase 3 — Wiki generation + lint (6/6)

| # | Scenario | Result |
| --- | --- | --- |
| 3.1 | Source page on ingest | PASS (4 source pages) |
| 3.2 | `pages build` (expect 0) | PASS |
| 3.3 | Clean-vault lint | PASS |
| 3.4 | Lint catches missing-slug | PASS (exit 1 on bad, exit 0 after restore) |
| 3.5 | Concept synthesis (stub) | PASS |
| 3.6 | Revision recorded with `generator=synth` | PASS |

## Phase 4 — Derived indexes (6/6)

| # | Scenario | Result |
| --- | --- | --- |
| 4.1 | OpenSearch + Qdrant up | PASS |
| 4.2 | `reindex all` | PASS (38 indexed) |
| 4.3 | `index sync` + status | PASS |
| 4.4 | OpenSearch query (`q=body:psychological`) | PASS (3 hits) |
| 4.5 | Qdrant query (`query_points`) | PASS (3 results) |
| 4.6 | Deterministic rebuild after drop | PASS |

## Phase 5 — Page-first retrieval (4/4)

| # | Scenario | Result |
| --- | --- | --- |
| 5.1 | Covered query | PASS (cov > 0.5, no fallback, ≥ 3 pages) |
| 5.2 | JSON output schema | PASS (all required keys) |
| 5.3 | Gap → chunk fallback (both pages indexes recreated empty) | PASS (cov 0, fallback true, 0 pages) |
| 5.4 | Traces persisted (`query_embedding` length 1024) | PASS |

## Phase 6 — Memgraph structural index (6/6)

| # | Scenario | Result |
| --- | --- | --- |
| 6.1 | Memgraph up | PASS |
| 6.2 | `graph rebuild` | PASS |
| 6.3 | `graph status` (`PART_OF` populated) | PASS |
| 6.4 | Acceptance Cypher (Source ↔ Concept via Chunk) | PASS (2 pairs) |
| 6.5 | Sync after re-ingest drains queue | PASS |
| 6.6 | Unreachable handling exits 1, no traceback | PASS |

## Phase 7 — Traces and revisions (5/5)

| # | Scenario | Result |
| --- | --- | --- |
| 7.1 | `trace list` / `trace show` (JSON shape) | PASS |
| 7.2 | Replay no-persist (trace count unchanged 3 → 3) | PASS |
| 7.3 | Replay `--persist` (count 3 → 4) | PASS |
| 7.4 | Revisions list + diff (2 revisions after re-synth) | PASS |
| 7.5 | Promote + reject second promote (exit 1) | PASS |

## Phase 8 — TUI

SKIPPED — interactive Textual UI requires TTY; manual walk per the
existing smoke playbook.

## Phase 9 — Curation loop (7/8 + 1 SKIPPED)

| # | Scenario | Result |
| --- | --- | --- |
| 9.1 | Create a gap (drop pages, run query) | PASS |
| 9.2 | `curate run` inserts signals | PASS |
| 9.3 | `curate list` shows open signals | PASS |
| 9.4 | `curate synth` from a signal | PASS (drafted) |
| 9.5 | Promote closes the loop | PASS (draft → canonical) |
| 9.6 | Replay improved (gap trace) | PASS (coverage 0.0 → positive delta) |
| 9.7 | Fast-loop expansion via `graph link` | PASS (`graph_expansion.reached` populated) |
| 9.8 | TUI curate | SKIPPED (interactive) |

## Phase 10 — Golden + CI (5/5)

| # | Scenario | Result | Detail |
| --- | --- | --- | --- |
| 10.1 | Full suite | PASS | 100 passed, 1 skipped, 2 deselected, 40.59 s |
| 10.2 | Golden only | PASS | 2 passed, 101 deselected, 6.75 s |
| 10.3 | Fast tier (`-m "not golden"`) | PASS | 98 passed, 3 skipped, 2 deselected, 34.47 s |
| 10.4 | Regression detector | PASS | 1 passed, 5.89 s |
| 10.5 | CI workflow has both jobs + 4 service containers | PASS |

## v0.2 Phase 1 — Real-model walk (5/5)

Stubs unset; `.env` configured for OpenRouter on both seams.

| # | Scenario | Result | Detail |
| --- | --- | --- | --- |
| v0.2-1.1 | `pytest -m live` | PASS | 2 passed, 101 deselected, 9.87 s |
| v0.2-1.2 | Qdrant point is real | PASS | dims=1024, norm=1.000000, equals stub False |
| v0.2-1.3 | Real synth output | PASS | `errors as information` page, 2673 bytes, H1 + sections, no stub phrase, 9 s wall |
| v0.2-1.4 | Focused real-model walk (query + graph + curate + trace) | PASS | cov=0.764, no fallback, 5 pages; graph 21/37; 2 new signals |
| v0.2-1.5 | Hermetic suite still green | PASS | 100 passed, 1 skipped, 2 deselected, 41.49 s |

## v0.2 Phase 2 — Backup / restore (6/6)

Stubs set throughout (deterministic baseline-vs-restore comparison).

| # | Scenario | Result | Detail |
| --- | --- | --- | --- |
| v0.2-2.1 | Local backup writes the pair | PASS | dump 87436 B + tar 4442 B |
| v0.2-2.2 | rsync mirror to `/tmp/cdb-test` | PASS | both files at destination, exit 0 |
| v0.2-2.3 | rsync failure isolation (bad SSH host) | PASS | local pair retained, exit 1 |
| v0.2-2.4 | Restore round-trip (drop DB + wipe vault + restore --force) | PASS | sources_after=5, vault_files=6 |
| v0.2-2.5 | Same answers after rebuild | PASS | baseline cov=0.7938 top=psychological-safety; restored cov=0.7938 top=psychological-safety (identical) |
| v0.2-2.6 | Schedule install + uninstall + idempotent uninstall | PASS | plist `Hour=3 Minute=15`; uninstall removes; second uninstall exits 0 with "not installed" |

## Cost summary

- v0.1 Phases 0–10: zero LLM/embeddings cost (stubs throughout).
- v0.2 Phase 1: ~10 OpenRouter calls (reindex + query + synth + 2
  live tests). Approximate spend well under $0.20.
- v0.2 Phase 2: zero LLM/embeddings cost (walk runs under stubs).

## Acceptance

All v0.1 and v0.2 phase acceptance criteria met on the merged stack.
Phase 8 + 9.8 remain manual (TUI interactive) per the smoke playbook
and do not regress any acceptance.
