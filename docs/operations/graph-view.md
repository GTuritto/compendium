# Graph view (WebUI)

A read-only view of the knowledge graph in the WebUI. `compendium web` → the
**Graph** view. It offers two **renderers** via a toggle at the top:

- **2D graphviz (typed edges)** — ADR-021, the dependency-free default/fallback.
- **3D galaxy (semantic similarity)** — ADR-023, an interactive 3D force-directed
  cloud.

Both are **read-only** (they never mutate the graph, pages, or any store — the
WebUI safe-only posture, ADR-020) and **bounded** (a node cap, so the browser
never renders an unbounded dump). Both share the *Scope* control — *Neighbourhood*
(search a focus node) or *Full graph (sampled)* — and the focus search.

## 2D graphviz (ADR-021)

Edges are Memgraph's **typed** relationships (PART_OF / EVIDENCES / GROUNDS /
RELATED_TO / PREREQUISITE_FOR / SYNTHESIZES / CONTRADICTS). Filters: node kinds
(Source/Concept/Topic/Chunk) and edge types. Rendered with `st.graphviz_chart`,
the force-directed layout requested inside the DOT (`layout="fdp"`) so it works
across Streamlit versions — no extra dependency. The export
(`graph/browse.py:graph_export`) issues MATCH/RETURN Cypher only.

## 3D galaxy (ADR-023)

Edges are **semantic similarity**: each page's top-K Qdrant nearest-neighbours
become undirected, similarity-weighted links kept at/above a threshold (a new
read-only export, `graph/semantic_export.py`, reusing the edge-extractor's
`nearest_neighbours`). Rendered with **vendored `3d-force-graph`** (three.js,
`compendium/web/static/`) through `st.components.v1.html` — **no pip dependency,
no CDN**, so the loopback WebUI works offline.

- **Visuals:** node colour by kind, node size by degree, edge width by similarity
  weight. Drag to orbit, scroll to zoom, drag a node; gentle auto-orbit until you
  interact.
- **Controls:** similarity threshold, neighbours-per-node (top-K), node cap, and
  a node-kind filter.
- **Click-to-open is deferred:** `st.components.v1.html` is a one-way embed, so a
  node click cannot navigate yet (a bidirectional component build is the
  follow-up). Use the focus selectbox to re-center; the galaxy is for visual
  exploration.

If Qdrant is unreachable the galaxy reports it; the 2D graphviz renderer (over
Memgraph) is the fallback. Tag-coloured / tag-filtered nodes and explicit-edge or
shared-tag galaxy modes are noted future upgrades.
