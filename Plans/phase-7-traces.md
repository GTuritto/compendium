# Phase 7 — Query traces and revision tracking: Implementation Plan

Date: 2026-05-26
Branch: `phase-7-traces` (off `main`)
OpenSpec change: `openspec/changes/phase-7-traces/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 7;
[docs/Compendium.md](../docs/Compendium.md) ADR-007.

## Goal

Everything the system did is inspectable. Replay is possible: replay a
historical query and see the diff; diff two revisions of a page; promotion
events show up in a list view.

## Why this plan exists

ADR-007's data already lands (Phase 5 writes `query_traces`, Phase 3 writes
`wiki_page_revisions`), but nothing reads it back, and `promotion_events` is
never written. This plan locks four decisions: (1) `trace replay` is read-only
by default and diffs the user-visible `final_ranking` (plus coverage/fallback),
not the noisy per-stage JSON; (2) `page diff` is a stdlib `difflib` unified body
diff plus a frontmatter key-delta; (3) `page promote` is a recorded transition
(revision + status flip + `promotion_events` row in one transaction), the reusable
primitive Phase 9's curator calls; (4) all SQL lives in `compendium/db/`, while
`compendium/trace/` holds DB-free diff/replay logic the Phase 8 TUI will import.

## Branch + commit strategy

- Create `phase-7-traces` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 7a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 7 complete — query traces and revision tracking`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### 7a — Repository read + promotion helpers

**Purpose:** The data-access layer telemetry reads through.

**Tasks:**

1. `get_query_trace(id)`, `list_query_traces(limit)` over `query_traces`.
2. `get_page_revisions(page_id)` (oldest-first), `get_revision(id)`, and a
   slug→page resolver (disambiguate by kind; error if ambiguous).
3. `record_promotion(...)` (insert `promotion_events`) and
   `list_promotion_events(slug=None, limit)`.

**Files modified:** `compendium/db/repository.py`
**Decision flagged:** all SQL stays in the repository module.

### 7b — Trace replay + ranking diff

**Purpose:** Replay a stored query and quantify what changed.

**Tasks:**

1. `compendium/trace/diff.py`: pure `ranking_diff(original, replayed)` →
   added / removed / moved pages, coverage delta, fallback change.
2. `compendium/trace/replay.py`: load trace, re-run
   `pipeline.query(query_text, persist=<flag>)`, return the diff. Read-only by
   default.

**Files added:** `compendium/trace/diff.py`, `compendium/trace/replay.py`
**Decision flagged:** read-only default (`--persist` opt-in); diff the final
ranking, not the whole pipeline JSON.

### 7c — Revision diff

**Purpose:** See how a page changed between two revisions.

**Tasks:**

1. `compendium/trace/revisions.py`: `body_diff(a, b)` (`difflib.unified_diff`)
   and `frontmatter_delta(a, b)` (added/removed/changed keys).
2. Resolve revisions by 1-based ordinal (oldest-first) or revision-id prefix.

**Files added:** `compendium/trace/revisions.py`
**Decision flagged:** stdlib `difflib`, no new dependency.

### 7d — Promotion logic

**Purpose:** Record a page lifecycle transition as a first-class event.

**Tasks:**

1. `compendium/trace/promote.py`: `promote(slug, to_status)` — one transaction:
   snapshot a `human` revision of the current body, update `wiki_pages.status`,
   `record_promotion` with the matching `promotion_kind`; reject invalid
   transitions.

**Files added:** `compendium/trace/promote.py`
**Decision flagged:** promotion writes a revision + event (not a bare status
update); `merge`/`split` kinds remain unexposed in v0.1; graph edge updates are
Phase 9.

### 7e — CLI

**Purpose:** The operator surface.

**Tasks:**

1. `compendium trace {list,show,replay}` (`replay <id> [--persist]`).
2. `compendium page revisions <slug>`, `compendium page diff <slug> <rev_a> <rev_b>`.
3. `compendium page promote <slug> --to {canonical,deprecated}`,
   `compendium promotions list [--slug <slug>]`.

**Files modified:** `compendium/__main__.py`
**Decision flagged:** `page` grows subcommands (`build` exists; add
`revisions`/`diff`/`promote`).

### 7f — Tests and acceptance

**Tasks:**

1. Unit: `ranking_diff`; `body_diff`/`frontmatter_delta` (change / no-change /
   key add-remove).
2. Integration (skip if stores unreachable, stub embedder): seed corpus + query;
   replay shows no-op diff on an unchanged corpus and a real diff after a page is
   added; read-only writes no trace, `--persist` writes one.
3. Revision: produce ≥2 revisions; `page revisions` lists them; `page diff`
   shows the change.
4. Promotion: `promote --to canonical` flips status + writes a
   `draft_to_canonical` event; `promotions list` shows it; `--slug` filters.
5. Append the Phase 7 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/test_telemetry.py`
**Files modified:** `tests/manual/smoke_test.md`

## Final file tree after Phase 7

```text
compendium/
  trace/
    __init__.py          (existing stub; gains exports)
    diff.py              NEW — ranking diff (pure)
    replay.py            NEW — load trace, re-run pipeline, diff
    revisions.py         NEW — body/frontmatter diff (difflib)
    promote.py           NEW — recorded promotion transition
  db/repository.py       MOD — trace/revision/promotion read + record helpers
  __main__.py            MOD — trace / page diff|revisions|promote / promotions CLI
tests/
  test_telemetry.py      NEW
  manual/smoke_test.md   MOD — § Phase 7
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | ranking_diff | added/removed/moved pages + coverage/fallback deltas correct |
| 2 | unit | body/frontmatter diff | unified diff on change; empty on identical; key add/remove/change detected |
| 3 | integration | replay unchanged corpus | diff is empty / no-op |
| 4 | integration | replay after a page is added | diff shows the new/added page and coverage delta |
| 5 | integration | replay persistence | default writes no trace; `--persist` writes exactly one |
| 6 | integration | revisions + diff | ≥2 revisions listed; diff shows the change |
| 7 | integration | promotion | status flips; `draft_to_canonical` event with from/to revs; listed; `--slug` filters |

## Per-phase smoke test

Appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 7.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 7.1 | Trace list/show | run a query, then `uv run python -m compendium trace list` and `trace show <id>` | the query's trace is listed; show renders its pipeline/ranking/coverage |
| 7.2 | Replay (read-only) | `uv run python -m compendium trace replay <id>` | prints the original-vs-current diff; `query_traces` row count unchanged |
| 7.3 | Replay persists | `... trace replay <id> --persist` | a new `query_traces` row is written |
| 7.4 | Revision diff | `uv run python -m compendium page revisions <slug>` then `page diff <slug> 1 2` | revisions listed; unified body diff + frontmatter delta shown |
| 7.5 | Promote + list | `uv run python -m compendium page promote <slug> --to canonical` then `promotions list` | status canonical; a `draft_to_canonical` event listed with timestamp |

## Out of scope for Phase 7 (do NOT build)

- TUI screens rendering traces/revisions/promotions — Phase 8 (imports this phase's diff/replay functions).
- Curator slow-loop generating promotions from `graph_curation_signals` — Phase 9.
- Graph side effects of promotion (new `GROUNDS`/`SYNTHESIZES` edges) — Phase 9.
- `merge`/`split` promotion kinds as commands — later.
- Delta/compressed revision storage; trace TTL/pruning — v0.2.

## Open questions — resolved at the review gate (2026-05-26)

1. **Revision addressing.** RESOLVED: 1-based ordinal (oldest-first) is primary;
   a revision-id prefix is also accepted.
2. **`promotions list` scope.** RESOLVED: bare command lists globally
   (most recent first); `--slug` filters to one page.
3. **Replay diff granularity.** RESOLVED: diff the user-visible `final_ranking`
   plus coverage/fallback deltas; full per-stage inspection stays in `trace show`.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 7 met.
- [ ] PR marked ready for review.
