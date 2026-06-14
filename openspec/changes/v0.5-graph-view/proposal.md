# Proposal — v0.5: graph / galaxy visualization in the WebUI

## Why

The knowledge graph already exists in Memgraph (Source/Concept/Topic/Chunk
nodes; PART_OF / EVIDENCES / GROUNDS / RELATED_TO / PREREQUISITE_FOR /
SYNTHESIZES / CONTRADICTS edges) and the TUI has a text-based graph browser, but
there is no visual, Obsidian-style view of the relationships. This change adds a
read-only force-directed "galaxy" graph to the WebUI. Parked behind the v0.4
verdict (`docs/proposals/README.md` §5). Read-only, so it fits the WebUI
safe-only posture (ADR-020).

## What Changes

- **Ships ADR-021** — a read-only graph visualization view in the WebUI.
- **A graph-read path.** A read-only graph export (a small facade/provider
  function) returns nodes + typed edges for a scope (a page's neighbourhood by
  default, the full graph as an option) from Memgraph, with limits/sampling so
  large graphs stay renderable.
- **The WebUI view.** A force-directed interactive graph: filter by node kind,
  edge type, and tag (ties to the tagging change); click a node to open the
  underlying page. Default to a neighbourhood-of-a-page view; full-graph is an
  option with a node cap.
- **A renderer dependency, weighed.** Streamlit needs a graph component
  (pyvis/vis-network HTML embed, streamlit-agraph, or d3); the choice is made in
  the plan against stack discipline (the WebUI itself is ADR-015; a viz lib is
  incremental).

## Impact

New: a read-only graph-export function; a WebUI graph view; one viz dependency
(decided in the plan); ADR-021 inline in `docs/Compendium.md`;
`docs/operations/graph-view.md`; tests (headless render + the export function).
Modified: `compendium/web/...`, possibly `compendium/api/facade.py` (a read-only
graph verb) and `pyproject.toml` (the viz dep), CHANGELOG, smoke playbook. **No
schema migration.** Version bump per policy.

## Gates

Parked behind the v0.4 verdict. Build-ready spec only. Best sequenced after
tagging (for tag-based filtering) and the admin surface (shares the WebUI work),
but independent enough to build alone.
