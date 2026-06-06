## Context

Third post-v0.2 architecture-deepening change (architecture review 2026-06-06, candidate 2). It consolidates the per-page-kind rules that v0.1 Phase 3 spread across `wiki/page.py`, `wiki/lint.py`, and `wiki/vault.py`. It adds no behaviour; it relocates the rules to one strategy registry. Independent of arch fixes 1 and 2 (disjoint packages); touches none of the May-26 reviews' settled verdicts.

Deepening target, in the review's vocabulary: a **missing seam** — the page kind is a real axis of variation, but it is expressed as three parallel `if/elif kind` ladders rather than one interface. The win is **locality**: a kind's required fields, frontmatter shape, DB fields, subdir, and lint rules are stated once, so a change touches one record and a new kind is one entry.

## Goals / Non-Goals

**Goals:**

- One `PageKind` registry as the single home for each kind's `subdir`, `required_fields`, `frontmatter_fields(page)`, `db_fields(page)`, and lint hooks (per-page + cross-page).
- `page.py`, `lint.py`, `vault.py` consult the registry instead of branching on `kind`.
- Behaviour preserved exactly: same frontmatter bytes + order, same lint rules/severities/messages, same DB columns, same vault subdirs.
- `Page` stays a flat dataclass — no change to its fields, construction, parsing, or attribute access.

**Non-Goals:**

- Subclassing `Page` (blast radius, no behaviour gain).
- Changing any kind's fields, rules, subdirs, or the frontmatter contract.
- Adding a fourth kind.

## Decisions

### Decision: a `PageKind` strategy registry, not `Page` subclasses

`compendium/wiki/page_kind.py` holds a `PageKind` record per kind and a `PAGE_KINDS: dict[str, PageKind]` registry. `Page` remains the single flat dataclass it is today. Rationale: `Page` is constructed and read field-by-field across ingest, synth, `source_page`, `parse_markdown`, `repository` round-trips, `trace/revisions`, and the TUI. Subclassing would force every one of those sites to change for zero behaviour gain. A strategy object captures the *rules* (the actual scatter) while leaving the *carrier* alone — the same shape fix 2 used for `EdgeType`.

```text
PageKind(
    name: str,                         # "concept" | "topic" | "source"
    subdir: str,                       # "concepts" | "topics" | "sources"
    required_fields: tuple[str, ...],  # additional, beyond REQUIRED_ALL
    frontmatter_fields: (Page) -> dict,    # kind-specific frontmatter, contract order
    db_fields: (Page) -> dict,             # kind-specific values for the vault DB write
    writes_topic_links: bool,          # concept-only post-write step
    lint_page: (Page, add) -> None,        # per-page kind rules
    lint_vault: (Page, ctx, add) -> None,  # cross-page kind rules
)
```

`frontmatter_fields` returns exactly the entries each `if/elif` branch in `Page.frontmatter()` adds today, in the same order — so the YAML is byte-identical. `db_fields` returns the kind-specific subset of the dict `vault.write_page` builds today.

### Decision: the lint rules move as hooks, iterated by the existing entry points

`lint_page(page)` keeps the universal checks (required-all, kind-in-set, slug rules, alias dup/title) and delegates the per-kind required-field check to `PAGE_KINDS[page.kind].lint_page`. `lint_vault(pages, ...)` keeps building its cross-page context (the topic-id set, the `by_id` map, `known_source_ids`) and passes that context to each page's `PAGE_KINDS[page.kind].lint_vault`, which runs the kind's resolution rule (concept→topic-ids, topic→parent + cycle, source→source-id). The `add(rule, severity, message)` closure is passed in, so rule names, severities, and messages are emitted verbatim.

**Alternative considered:** move the universal checks into the registry too. Rejected — they are not per-kind; keeping them in `lint_page`/`lint_vault` and delegating only the kind-specific parts is the minimal, clearest split.

### Decision: `vault.write_page` consults `db_fields` and the registry subdir

The kind-specific values in the `insert_wiki_page` / `update_wiki_page` field dict come from `PAGE_KINDS[page.kind].db_fields(page)` (which yields the same `aliases` / `parent_topic_id` / `source_*` values, UUID-coerced as today). `_SUBDIR` is replaced by `PAGE_KINDS[page.kind].subdir`. The concept-only topic-link write is gated by `writes_topic_links` (or a small hook), preserving the current `if page.kind == "concept"` behaviour.

### Decision: `REQUIRED_BY_KIND` and `PAGE_KINDS` (the name tuple) derive from the registry

`page.py` keeps the public names `PAGE_KINDS` (the tuple of kind names) and `REQUIRED_BY_KIND` (the dict) for existing importers, but both are computed from the registry so there is one source. `REQUIRED_ALL`, `PAGE_STATUSES`, `GENERATORS` are unchanged.

## Risks / Trade-offs

- **Frontmatter byte-drift.** The highest-value invariant. Mitigation: a test asserts `Page.frontmatter()` and `to_markdown()` produce byte-identical output to the pre-refactor code for a fixture of each kind (captured as expected strings), and the existing `test_wiki` round-trip tests stay green.
- **Lint output drift.** Mitigation: the `add(...)` closure is threaded through unchanged, and the existing lint tests assert rule names/severities; they must stay green.
- **A circular import** (`page_kind.py` referencing `Page`). Mitigation: the hooks take a `Page` parameter and `page_kind.py` imports `Page` only for typing (or uses `from __future__ import annotations` + duck typing); `page.py` imports the registry. Keep `PageKind` free of `lint`/`vault` imports so the dependency is one-way.

## Migration Plan

Pure refactor; no data or schema. Land `page_kind.py` + tests first, then point `page.frontmatter()`/`REQUIRED_BY_KIND` at it, then `lint.py`, then `vault.py`; each step green with the existing wiki/lint suites. Rollback = revert the branch.

## Open Questions

- Should `vault.write_page`'s DB-field building route fully through `db_fields` (recommended — full locality), or keep the UUID-coercion in `vault.py` and only source the raw values from the registry? (Plan: route the kind-specific values through `db_fields`, keep the UUID coercion at the vault boundary where the DB types live.)
- Keep `REQUIRED_BY_KIND` as a derived public name, or drop it if unused outside `page.py`? (Plan: keep it derived — cheap, and avoids breaking any importer.)
