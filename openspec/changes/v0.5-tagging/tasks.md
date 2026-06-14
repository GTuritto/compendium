# Tasks — v0.5-tagging

Gated on: the v0.4 verdict per `docs/proposals/README.md`. Build-ready spec only.

- [ ] 1a schema + repository: migration for `tags` + `source_tags` / `page_tags`
  (array-column alternative decided in the plan); tags repository functions
  (add/remove/list, attach/detach); ADR-019 inline in `docs/Compendium.md`.
- [ ] 1b index propagation: tag field in the OpenSearch mapping and the Qdrant
  payload; `reindex` / sync writes tags; mapping/payload tests.
- [ ] 1c retrieval filter: optional tag filter on `pipeline.run`/`query`,
  enforced at the index; filter recorded in the trace; unfiltered path proven
  unchanged.
- [ ] 1d surfaces: `compendium tag add/rm/ls` and `--tag` on `query`/`ask`;
  TUI tag + filter controls; WebUI tag + filter (non-destructive).
- [ ] 1e docs + close: `docs/operations/tagging.md`; CHANGELOG; smoke section;
  full fast + golden green; version bump in the completion commit.
