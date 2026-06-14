# Tasks — v0.5-graph-view

Gated on: the v0.4 verdict per `docs/proposals/README.md`. Build-ready spec only.

- [ ] 1a graph-read path: a read-only graph export (nodes + typed edges) over
  Memgraph, scoped (page neighbourhood / bounded full graph) with a node cap;
  tests; ADR-021 inline in `docs/Compendium.md`.
- [ ] 1b renderer decision + dependency: choose the Streamlit graph component
  (pyvis / streamlit-agraph / d3) per stack discipline; add the dep.
- [ ] 1c WebUI view: force-directed render; filter by node kind / edge type /
  tag; node click opens the page; read-only; headless test.
- [ ] 1d docs + close: `docs/operations/graph-view.md`; CHANGELOG; smoke
  section; full fast + golden green; version bump in the completion commit.
