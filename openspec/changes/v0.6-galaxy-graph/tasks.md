# Tasks — v0.6-galaxy-graph

Follows ADR-021 (merged). Docs-first: this change + the Phase Plan land before
any implementation code; sub-phase commits only after the plan is approved.

- [ ] 1a semantic-similarity export: a read-only `{nodes, links}` export built
  from Qdrant kNN (reuse `nearest_neighbours`), scoped (page neighbourhood /
  bounded full graph), with a node cap, top-K, and a similarity threshold;
  similarity-weighted undirected edges. Hermetic tests with a stub Qdrant.
  ADR-023 inline in `docs/Compendium.md`.
- [ ] 1b renderer + vendored asset: vendor `3d-force-graph` (minified) under
  `compendium/web/static/`; a pure payload+HTML builder (no I/O, no Streamlit)
  analogous to `graphviz.py`; hermetic builder test. Confirm no pip dependency.
- [ ] 1c WebUI galaxy mode: a 2D-graphviz | 3D-galaxy toggle in the Graph view;
  `st.components.v1.html` render of the builder output; node colour by kind,
  size by degree, edge width by similarity; threshold/top-K/node-cap/kind
  controls; read-only; headless builder test. Graphviz stays the no-JS fallback.
- [ ] 1d docs + close: update `docs/operations/graph-view.md` (galaxy section);
  CHANGELOG; smoke section; full fast + golden green; version bump in the
  completion commit.
