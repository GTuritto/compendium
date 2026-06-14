# Proposal — v0.5: tagging

## Why

The corpus has no lightweight, user-applied organization. Topics (ADR-006) are
synthesized structural groupings and aliases feed recall; neither lets the
curator say "this source is for project-x" or "ask only within my trading
reading." Tagging adds orthogonal, curator-assigned labels that also scope
retrieval. Parked behind the v0.4 verdict (`docs/proposals/README.md` §3); this
formalizes the requirement. Design fixed 2026-06-14: retrieval-filter grade,
on sources and pages, curator-assigned.

## What Changes

- **Tags as system-of-record data (ships ADR-019).** PostgreSQL gains tags and
  their attachments to sources and wiki pages (a `tags` table plus
  `source_tags` / `page_tags` joins; the array-column alternative is weighed in
  the plan). One schema migration. Tags are explicitly **not** topics and
  **not** aliases.
- **Retrieval filtering.** Tags propagate into the OpenSearch and Qdrant
  payloads as a filterable field on `reindex` / sync. The retrieval pipeline
  gains an optional tag filter (`pipeline.run`/`query`), and the query trace
  records the filter that was applied.
- **Assign and filter across all surfaces.** CLI (`compendium tag add/rm/ls`
  and a `--tag` filter on `query`/`ask`), the TUI (tag a source/page; filter
  lists), and the WebUI (assign + filter; safe, non-destructive, so it fits the
  WebUI per ADR-020).

## Impact

New: a migration (tags + join tables); a tags repository module; the `tag` CLI
verbs and the `--tag` filter; TUI + WebUI tag controls; ADR-019 inline in
`docs/Compendium.md`; `docs/operations/tagging.md`; `tests/test_tagging.py`.
Modified: `repository.py`, `compendium/index/*` (payload field + mapping),
`compendium/retrieve/pipeline.py` + `search.py` (the filter), `__main__.py`,
TUI/WebUI, CHANGELOG, smoke playbook. Version bump per policy.

## Gates

Parked behind the v0.4 verdict. Build-ready spec only until then. (Note: if
tagging is unparked before the curation/admin items, it is the filter
dimension several of them reuse — see the sequencing note in
`docs/proposals/README.md`.)
