# Tasks — arch-page-kind-seam

Behaviour-preserving consolidation of per-page-kind rules into one `PageKind` strategy registry, consulted by `page.py` / `lint.py` / `vault.py`. `Page` stays a flat dataclass. No schema migration; no new dependency; no output change. One commit per sub-phase, green at HEAD. Boxes unchecked until implementation is approved.

## 1. The `PageKind` registry (sub-phase a)

- [ ] 1.1 `compendium/wiki/page_kind.py`: a `PageKind` record (`name`, `subdir`, `required_fields`, `frontmatter_fields(page)`, `db_fields(page)`, `writes_topic_links`, `lint_page(page, add)`, `lint_vault(page, ctx, add)`) and a `PAGE_KINDS: dict[str, PageKind]` registry for `concept` / `topic` / `source`. Values mirror today's behaviour exactly. Import `Page` for typing only (one-way dependency; no `lint`/`vault` imports).
- [ ] 1.2 `frontmatter_fields` for each kind returns exactly the entries the current `Page.frontmatter()` `if/elif` adds, in the same order; `db_fields` returns the kind-specific values the current `vault.write_page` builds (raw values; UUID coercion stays at the vault boundary).
- [ ] 1.3 `tests/test_page_kind.py`: assert the registry has the three kinds; `required_fields` per kind match the current `REQUIRED_BY_KIND`; `frontmatter_fields` for a sample page of each kind equals the current expected dict (keys + order).

## 2. `page.py` consults the registry (sub-phase b)

- [ ] 2.1 `Page.frontmatter()`: replace the `if/elif kind` block with `data.update(PAGE_KINDS[self.kind].frontmatter_fields(self))`.
- [ ] 2.2 Derive `REQUIRED_BY_KIND` and `PAGE_KINDS` (the kind-name tuple) from the registry; keep the public names. `REQUIRED_ALL` / `PAGE_STATUSES` / `GENERATORS` unchanged.
- [ ] 2.3 A byte-identical test: `to_markdown()` for a fixture of each kind matches a captured pre-refactor string; existing `test_wiki` round-trip tests green.

## 3. `lint.py` consults the registry (sub-phase c)

- [ ] 3.1 `lint_page`: keep the universal checks (required-all, kind-in-set, slug, alias dup/title); delegate the per-kind required-field check to `PAGE_KINDS[page.kind].lint_page(page, add)`.
- [ ] 3.2 `lint_vault`: keep building the cross-page context (topic-id set, `by_id`, `known_source_ids`); delegate the per-kind resolution rules (concept topic-ids, topic parent + cycle, source source-id) to `PAGE_KINDS[page.kind].lint_vault(page, ctx, add)`. Rule names / severities / messages emitted verbatim via the `add` closure.
- [ ] 3.3 Existing lint tests green (same rules fire with same severities on the same fixtures).

## 4. `vault.py` consults the registry + close-out (sub-phase d)

- [ ] 4.1 `write_page`: source the kind-specific field values from `PAGE_KINDS[page.kind].db_fields(page)` (UUID coercion stays at the vault boundary); gate the topic-link write by `writes_topic_links`; replace `_SUBDIR` with `PAGE_KINDS[page.kind].subdir`.
- [ ] 4.2 Grep gate (a test or smoke note): no `page.kind ==` / `kind == "concept"|"topic"|"source"` conditional remains in `page.py` / `lint.py` / `vault.py`; the per-kind rules live only in `page_kind.py`.
- [ ] 4.3 `docs/Compendium.md` (Part I / ADR-001 area): a one-line note that per-kind page rules live in `compendium/wiki/page_kind.py`. `CONTEXT.md`: add **page kind** as a first-class strategy record (the home for a kind's frontmatter / required fields / DB fields / subdir / lint rules).
- [ ] 4.4 Append an "Arch fix 3" smoke section to `tests/manual/smoke_test.md`: synth a concept + generate a source page, `lint` clean; inspect that frontmatter + subdirs are unchanged; break a per-kind field and confirm the same lint rule fires.
- [ ] 4.5 **Acceptance:** the per-kind rules live only in `page_kind.py`; `page.py`/`lint.py`/`vault.py` carry no `kind ==` conditional; frontmatter bytes, lint output, DB rows, and subdirs are identical; `Page` construction/parse/attribute access unchanged; `tests/test_page_kind.py` plus the existing wiki/lint suites green; fast tier and golden green.
- [ ] 4.6 `openspec validate arch-page-kind-seam` clean.
