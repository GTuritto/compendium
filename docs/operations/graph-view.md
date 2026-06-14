# Graph view (WebUI)

A read-only, force-directed view of the knowledge graph in the WebUI (ADR-021).
`compendium web` → the **Graph** view.

- **Scope:** *Neighbourhood* (search a focus node, see its neighbours within a
  few hops) or *Full graph (sampled)* — both **bounded** (node cap) so the
  browser never renders an unbounded dump.
- **Filters:** node kinds (Source/Concept/Topic/Chunk) and edge types
  (PART_OF / EVIDENCES / GROUNDS / RELATED_TO / PREREQUISITE_FOR / SYNTHESIZES /
  CONTRADICTS).
- **Re-center:** pick a focus node to re-render its neighbourhood.
- **Read-only:** the view never mutates the graph or pages (it fits the WebUI
  safe-only posture, ADR-020). The export issues MATCH/RETURN Cypher only.

Rendered with `st.graphviz_chart(engine="fdp")` — a force-directed layout with
no extra dependency. `graphviz_chart` has no click events, so opening a node's
page is via the focus selectbox rather than a direct click; an interactive
component (streamlit-agraph) plus tag-coloured nodes are noted future upgrades.
