"""Pure DOT builder for the WebUI graph view (ADR-021).

No I/O, no Streamlit: a graph export dict in, a Graphviz DOT string out. The
WebUI renders it with ``st.graphviz_chart(dot, engine="fdp")`` (a force-directed
layout, no extra dependency — Streamlit renders the DOT string client-side).
Read-only by construction: it only emits ``digraph`` text.
"""

from __future__ import annotations

from typing import Any

_KIND_COLOR = {
    "Source": "#9aa7ff",
    "Concept": "#5fcf97",
    "Topic": "#ffb45f",
    "Chunk": "#cfd3d6",
}


def _esc(text: str) -> str:
    return (text or "").replace("\\", "").replace('"', "'")


def build_dot(
    export: dict[str, Any],
    *,
    kinds: set[str] | None = None,
    edge_types: set[str] | None = None,
) -> str:
    """Build a Graphviz ``digraph`` from a ``browse.graph_export`` payload.

    ``kinds`` keeps only those node labels; ``edge_types`` keeps only those edge
    types. Edges to filtered-out nodes are dropped.
    """
    nodes = export.get("nodes", [])
    edges = export.get("edges", [])
    if kinds:
        nodes = [n for n in nodes if n.get("kind") in kinds]
    keep = {n["id"] for n in nodes}

    lines = ['digraph "g" {', "  node [style=filled, shape=ellipse, fontsize=10];"]
    for n in nodes:
        color = _KIND_COLOR.get(n.get("kind", ""), "#dddddd")
        label = _esc(n.get("label") or n["id"])[:30]
        lines.append(f'  "{n["id"]}" [label="{label}", fillcolor="{color}"];')
    for e in edges:
        if e["from_id"] not in keep or e["to_id"] not in keep:
            continue
        if edge_types and e["type"] not in edge_types:
            continue
        lines.append(
            f'  "{e["from_id"]}" -> "{e["to_id"]}" '
            f'[label="{e["type"]}", fontsize=8, color="#888888"];'
        )
    lines.append("}")
    return "\n".join(lines)
