# Proposal — v0.6: interactive 3D knowledge-galaxy in the WebUI

## Why

ADR-021 shipped a read-only graph view rendered with `st.graphviz_chart` — a
static, force-directed image with no drag, hover, zoom, or click, and edges
limited to Memgraph's typed relationships. Its own operations doc names the next
step: "an interactive component plus tag-coloured nodes are noted future
upgrades." This change delivers that upgrade as an interactive **3D
knowledge-galaxy**: nodes drift in 3D space, cluster by subject, and connect by
**semantic similarity** (the signal that makes the "cloud" effect), inspired by
agentic-patterns.com/graph. It stays read-only, so it keeps the WebUI safe-only
posture (ADR-020).

## What Changes

- **Ships ADR-023** — an interactive 3D semantic-similarity graph view in the
  WebUI, extending (not replacing) the read-only ADR-021 graph view.
- **A semantic-similarity export.** A new bounded, read-only export builds a
  `{nodes, links}` payload from **Qdrant nearest-neighbours** (reusing
  `nearest_neighbours()` in `compendium/curate/extract.py`): for each page in
  scope, take its top-K neighbours and emit undirected, similarity-weighted
  edges above a threshold. This is a **sibling** to `graph/browse.py:graph_export`
  (which emits Memgraph typed edges), not a change to it.
- **The renderer: `3d-force-graph` (three.js), no pip dependency.** Rendered via
  `st.components.v1.html` (the WebUI's first `st.components` use), fed the JSON
  payload. The JS is **vendored** locally so the loopback WebUI stays
  offline-clean (no runtime CDN). A pure payload+HTML builder (analogous to
  `compendium/web/graphviz.py`) keeps the I/O out of the renderer.
- **The view.** Node colour by kind (on-brand `_KIND_COLOR`), node size by
  degree, edge width by similarity weight, hover labels, drag/orbit/zoom, gentle
  auto-orbit. Controls: a similarity-threshold slider, top-K, node cap, and a
  node-kind filter. Added as a **mode toggle** in the existing Graph view
  (2D graphviz | 3D galaxy), keeping graphviz as the no-JS fallback.

## Impact

New: a semantic-similarity graph export; a vendored `3d-force-graph` asset + a
pure payload/HTML builder under `compendium/web/`; the galaxy mode in the WebUI
Graph view; ADR-023 inline in `docs/Compendium.md`; an updated
`docs/operations/graph-view.md`; tests (export logic with a stub Qdrant +
hermetic payload/HTML builder). Modified: `compendium/web/...`,
`compendium/graph/` or a new `compendium/graph/semantic_export.py`, CHANGELOG,
smoke playbook. **No pip dependency. No schema migration.** Version bump per
policy.

## Gates

Follows ADR-021 (must be merged — it is). Best after tagging (for an optional
tag filter later) but independent. The one-way `st.components.v1.html` embed
means **click-to-open-page is a noted follow-up** (needs a bidirectional
component build); v1 uses the galaxy for visual exploration plus the existing
focus selectbox for navigation. The version label (`v0.6`) is provisional.
