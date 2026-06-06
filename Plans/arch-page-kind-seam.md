# Arch fix 3 — PageKind strategy registry: Implementation Plan

Date: 2026-06-06
Branch: `arch/page-kinds` (off `main`)
OpenSpec change: `openspec/changes/arch-page-kind-seam/`
Spec source: architecture review 2026-06-06 (candidate 2, "Strong"); preserves
ADR-001 + the frontmatter contract. Independent of arch fixes 1 and 2.

## Goal

Consolidate the per-page-kind rules (required fields, frontmatter shape, DB
fields, vault subdir, lint rules) — today scattered as `if/elif kind` ladders in
`wiki/page.py`, `wiki/lint.py`, and `wiki/vault.py` — into one `PageKind`
strategy registry the three modules consult. `Page` stays a flat data carrier.

## Why this plan exists

It locks in that this is a **rule relocation, not a model change**: the `Page`
dataclass and every construction/parse/attribute-access site are untouched (so
no blast radius across ingest/synth/repository/traces/TUI), and the output is
byte-for-byte identical (asserted by frontmatter/Markdown golden strings per
kind and the existing lint tests). It fixes the order so each consumer is
migrated behind the registry one commit at a time, green throughout.

## Branch + commit strategy

- Create `arch/page-kinds` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch3a — PageKind registry`, `Arch3b — page.py`, …), green at HEAD.
- Final commit: `Arch fix 3 complete — PageKind strategy registry`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — The `PageKind` registry

**Purpose:** Land the single home for per-kind rules with zero consumers changed.

**Tasks:** `page_kind.py` (record + registry: subdir, required_fields, frontmatter_fields, db_fields, writes_topic_links, lint hooks); `test_page_kind.py` (three kinds; required-fields match; frontmatter_fields per kind equals the expected dict + order).

**Files added:** `compendium/wiki/page_kind.py`, `tests/test_page_kind.py`
**Files modified:** none yet
**Decision flagged:** strategy registry, not `Page` subclasses; `Page` stays flat; one-way dependency (`page_kind` imports `Page` for typing only).

### b — `page.py` consults the registry

**Purpose:** Frontmatter + required-fields from the registry.

**Tasks:** `frontmatter()` uses `frontmatter_fields`; `REQUIRED_BY_KIND` + `PAGE_KINDS` derive from the registry. Byte-identical `to_markdown()` test per kind.

**Files modified:** `compendium/wiki/page.py`

### c — `lint.py` consults the registry

**Purpose:** Per-kind lint rules via hooks; universal checks stay.

**Tasks:** `lint_page` delegates the per-kind required-field check; `lint_vault` passes its cross-page context to each kind's `lint_vault` hook (concept topic-ids, topic parent + cycle, source source-id). `add()` threaded through so rule/severity/message are verbatim.

**Files modified:** `compendium/wiki/lint.py`

### d — `vault.py` consults the registry + close-out

**Purpose:** DB fields + subdir from the registry; docs + smoke; grep gate.

**Tasks:** `write_page` uses `db_fields` + `subdir`; topic-link write gated by `writes_topic_links`. Grep gate (no `kind ==` left in the three modules). `docs/Compendium.md` + `CONTEXT.md` notes. Smoke section. `openspec validate`.

**Files modified:** `compendium/wiki/vault.py`, `docs/Compendium.md`, `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
compendium/wiki/
  page_kind.py            # NEW — PageKind record + registry (per-kind rules)
  page.py                 # MODIFIED — frontmatter()/REQUIRED_BY_KIND from the registry
  lint.py                 # MODIFIED — per-kind rules via registry hooks
  vault.py                # MODIFIED — db_fields + subdir from the registry
tests/
  test_page_kind.py       # NEW
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | `PageKind` registry | three kinds; `required_fields` match current `REQUIRED_BY_KIND`; `frontmatter_fields` per kind = expected dict + order |
| 2 | unit | byte-identical frontmatter | `to_markdown()` for a fixture of each kind matches a captured pre-refactor string |
| 3 | regression | `test_wiki` round-trip | parse → render → parse stable; unchanged |
| 4 | regression | lint suite | same rules fire with same severities/messages on the same fixtures |
| 5 | grep gate | no `kind ==` in page/lint/vault | per-kind rules live only in `page_kind.py` |
| 6 | golden | `uv run pytest -m golden` | unaffected |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch3.1 | Frontmatter + subdirs unchanged | synth a concept; generate a source page; inspect `vault/concepts/*.md` + `vault/sources/*.md` | same frontmatter fields/order and same subdirs as before |
| arch3.2 | Lint clean | `compendium lint` on the seeded vault | 0 errors, exit 0 |
| arch3.3 | Per-kind lint still fires | drop a kind-required field (e.g. a concept's `topic_ids` resolution, or a source's `source_id`) | the same per-kind rule fires as before; exit 1 |

## Out of scope for this fix (do NOT build)

- Subclassing `Page` / changing the data model.
- Changing any kind's fields, lint rules, subdirs, or the frontmatter contract.
- Adding a fourth page kind.

## Open questions to confirm before starting

1. Route `vault.write_page` DB-field values fully through `db_fields` (recommended), keeping UUID coercion at the vault boundary, or only source raw values? Recommendation: `db_fields` returns raw values; vault coerces to DB types.
2. Keep `REQUIRED_BY_KIND` as a derived public name (recommended) or drop it? Recommendation: keep derived.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change complete and `openspec validate arch-page-kind-seam` clean.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke section appended to `tests/manual/smoke_test.md`.
- [ ] Acceptance (proposal / tasks § 4.5) met: rules only in `page_kind.py`; no `kind ==` in the three modules; identical frontmatter/lint/DB/subdirs; `Page` untouched.
- [ ] PR marked ready for review.
