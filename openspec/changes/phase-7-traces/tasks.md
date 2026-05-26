# Tasks — phase-7-traces

Implements Phase 7 of `docs/COMPENDIUM_BUILD.md`. No schema migration: the
`query_traces`, `wiki_page_revisions`, and `promotion_events` tables and the
`page_status`/`promotion_kind`/`page_generator` enums all exist from Phases 1/3/5.
Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. Repository read + promotion helpers (7a)

- [ ] 1.1 `compendium/db/repository.py`: `get_query_trace(id)` and `list_query_traces(limit)` over `query_traces`
- [ ] 1.2 `get_page_revisions(page_id)` (ordered oldest-first) and `get_revision(id)` over `wiki_page_revisions`; a slug→page resolver helper (disambiguate by kind, error if ambiguous)
- [ ] 1.3 `record_promotion(page_id, to_status, kind, from_rev, to_rev, notes)` (insert `promotion_events`) and `list_promotion_events(slug=None, limit)`

## 2. Trace replay + ranking diff (7b)

- [ ] 2.1 `compendium/trace/diff.py`: pure `ranking_diff(original_final_ranking, replayed_final_ranking)` → added / removed / moved pages, plus coverage and fallback deltas
- [ ] 2.2 `compendium/trace/replay.py`: load a trace, re-run `pipeline.query(query_text, persist=<flag>)` against the current corpus, return the diff; default read-only (`persist=False`)

## 3. Revision diff (7c)

- [ ] 3.1 `compendium/trace/revisions.py`: `body_diff(a, b)` (stdlib `difflib.unified_diff`) and `frontmatter_delta(a, b)` (added/removed/changed keys)
- [ ] 3.2 Resolve revisions by ordinal (1-based, oldest-first) or by revision-id prefix

## 4. Promotion logic (7d)

- [ ] 4.1 `compendium/trace/promote.py`: `promote(slug, to_status)` — in one transaction snapshot a `human` revision of the current body, update `wiki_pages.status`, and `record_promotion` with the matching `promotion_kind` (`draft_to_canonical` / `canonical_to_deprecated`); reject invalid transitions

## 5. CLI (7e)

- [ ] 5.1 `compendium trace {list,show,replay}` (`show <id>`, `replay <id> [--persist]`) in `compendium/__main__.py`
- [ ] 5.2 `compendium page revisions <slug>` and `compendium page diff <slug> <rev_a> <rev_b>`
- [ ] 5.3 `compendium page promote <slug> --to {canonical,deprecated}` and `compendium promotions list [--slug <slug>]`

## 6. Tests and acceptance (7f)

- [ ] 6.1 Unit: `ranking_diff` (added/removed/moved, coverage/fallback deltas); `body_diff`/`frontmatter_delta` (change, no-change, key add/remove)
- [ ] 6.2 Integration (skip if stores unreachable, stub embedder): seed a corpus + a query; `trace replay` shows no-op diff against an unchanged corpus and a real diff after a page is added; assert read-only replay writes no trace and `--persist` writes one
- [ ] 6.3 Revision test: synth twice (or edit), assert `page revisions` lists ≥2 and `page diff` shows the body/frontmatter change
- [ ] 6.4 Promotion test: `promote --to canonical` flips status, writes a `draft_to_canonical` event with from/to revisions; `promotions list` shows it; `--slug` filters
- [ ] 6.5 Append the Phase 7 smoke section to `tests/manual/smoke_test.md`; run it
- [ ] 6.6 **Acceptance:** replay a historical query and see the diff; diff two revisions of a page and see the change; promotion events appear in `compendium promotions list`. `uv run pytest` passes
