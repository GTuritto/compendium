## Why

The wiki has three page kinds — `source` (auto-generated, one per source), `concept` (synthesized, the artifact that compounds), and `topic` (structural) — and each has distinct required frontmatter fields, a distinct frontmatter shape, distinct per-page and cross-page lint rules, and a distinct vault subdirectory. Today that per-kind knowledge is **smeared across three modules as parallel `if/elif kind` ladders**, so "what a concept page *is*" has no single home and a change to one kind means editing every ladder, with nothing failing loudly if you miss one.

Verified scatter:

- `compendium/wiki/page.py`: `Page.frontmatter()` (`:102`) builds the kind-specific frontmatter via `if kind == "concept" / elif "topic" / elif "source"`; `REQUIRED_BY_KIND` (`:37`) lists per-kind required fields separately.
- `compendium/wiki/lint.py`: `lint_page` branches `if page.kind == "source"` for required fields (`:96`); `lint_vault` branches `concept` (topic-id resolution + alias collisions, `:129`), `topic` (parent resolution, `:138`), `source` (source-id resolution, `:144`), plus a `topic` cycle check (`:155`).
- `compendium/wiki/vault.py`: `write_page` builds the DB field dict with `aliases if kind=="concept"`, `parent_topic_id if kind=="topic"`, `source_* if kind=="source"` (`:75`), the `concept` topic-link write (`:108`), and `_SUBDIR[page.kind]` for the file path (`:66`).

This is a **missing seam**: the kind is a real axis of variation, but it is expressed as scattered conditionals instead of one polymorphic interface. The fix consolidates the per-kind rules into one `PageKind` strategy registry that `page.py`, `lint.py`, and `vault.py` consult — behaviour-preserving (same frontmatter, same lint, same DB fields, same subdirs); adding or changing a kind becomes one registry entry, not three synchronized edits.

The `Page` dataclass stays a **flat data carrier** (all its fields, construction sites, and attribute access are unchanged) — the consolidation is of the *rules*, not the data model. Subclassing `Page` into `SourcePage`/`ConceptPage`/`TopicPage` was considered and rejected for blast radius (every `Page(...)` constructor and `page.<field>` access across ingest, synth, parse, repository round-trips, traces, and the TUI would have to change for no behaviour gain).

## What Changes

- **A `PageKind` strategy registry** (`compendium/wiki/page_kind.py`): one record per kind carrying its `subdir`, its additional `required_fields`, a `frontmatter_fields(page)` function (the kind-specific frontmatter entries in contract order), `db_fields(page)` (the kind-specific values for the vault DB write), and the per-page and cross-page lint hooks. A `by_name` lookup; `PAGE_KINDS` derives from the registry.
- **`page.py` consults the registry.** `Page.frontmatter()` replaces its `if/elif` with `data.update(PAGE_KINDS[self.kind].frontmatter_fields(self))`; `REQUIRED_BY_KIND` is derived from each kind's `required_fields`. The `Page` dataclass is otherwise unchanged.
- **`lint.py` consults the registry.** The per-kind required-field check, the cross-page resolution rules (concept topic-ids, topic parent + cycle, source source-id), and the alias-collision rule move into the kind records' lint hooks; `lint_page` / `lint_vault` iterate and call them.
- **`vault.py` consults the registry.** The kind-specific DB field values come from `db_fields(page)`, the topic-link write is gated by a kind flag/hook, and `_SUBDIR` derives from the registry's `subdir`.

## Capabilities

### New Capabilities

- `page-kind-seam`: the `PageKind` strategy registry (`compendium/wiki/page_kind.py`) as the single home for each kind's required fields, frontmatter shape, DB fields, vault subdir, and lint rules; `page.py`, `lint.py`, and `vault.py` consult it instead of branching on `kind`. Behaviour-preserving across synth, ingest, parse, lint, and the vault write.

### Modified Capabilities

<!-- No behaviour change to ADR-001 (the Markdown wiki is canonical) or the
frontmatter contract: the same fields are emitted in the same order, the same
lint rules fire with the same severities, the same DB columns are written, and
pages land in the same subdirectories. The Page dataclass, parse_markdown, and
every construction site are unchanged. This relocates per-kind rules; it does
not change them. -->

## Impact

- **New code/files:** `compendium/wiki/page_kind.py` (the registry + per-kind records); `tests/test_page_kind.py`.
- **Modified files:** `compendium/wiki/page.py` (`frontmatter()` + `REQUIRED_BY_KIND` derive from the registry), `compendium/wiki/lint.py` (per-kind rules via the registry hooks), `compendium/wiki/vault.py` (`db_fields` + `_SUBDIR` from the registry); `tests/test_wiki.py` / `tests/test_lint*.py` as needed.
- **No schema migration. No new dependency.** Pure refactor over the existing dataclass + YAML frontmatter.
- **No output change.** Byte-identical frontmatter and Markdown; identical lint output (rules, severities, messages); identical DB rows; identical vault paths.
- **Out of scope:**
  - **Subclassing `Page`** — rejected (blast radius); `Page` stays a flat carrier.
  - **Adding or changing any kind's fields, rules, or subdirs** — strictly behaviour-preserving.
  - **A fourth page kind** — the registry makes one easy later, but none is added here.
  - **Frontmatter-contract or lint-rule changes** — none; the same rules relocate.
