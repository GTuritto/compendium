"""Graph/galaxy WebUI view (ADR-021, v0.5).

Hermetic: the DOT builder is pure; the read-only invariant is a source check.
The bounded-export test hits Memgraph and skips if it is unreachable.
"""

from __future__ import annotations

import inspect

import pytest


def _sample_export():
    return {
        "nodes": [
            {"id": "s1", "label": "A Source", "kind": "Source"},
            {"id": "c1", "label": "A Concept", "kind": "Concept"},
            {"id": "k1", "label": "chunk", "kind": "Chunk"},
        ],
        "edges": [
            {"type": "GROUNDS", "from_id": "c1", "to_id": "k1"},
            {"type": "RELATED_TO", "from_id": "c1", "to_id": "s1"},
        ],
    }


def test_build_dot_renders_nodes_and_edges():
    """TC-GV-U4: pure transform export -> Graphviz digraph."""
    from compendium.web.graphviz import build_dot

    dot = build_dot(_sample_export())
    assert dot.startswith("digraph")
    assert '"c1"' in dot and '"GROUNDS"' in dot
    assert "->" in dot  # directed
    assert 'layout="fdp"' in dot  # force-directed requested in the DOT, not via engine= kwarg


def test_build_dot_filters(_=None):
    """TC-GV-U5: node-kind and edge-type filters narrow the rendered set."""
    from compendium.web.graphviz import build_dot

    # only concepts: the Source/Chunk nodes and their edges drop out
    dot = build_dot(_sample_export(), kinds={"Concept"})
    assert '"c1"' in dot and '"s1"' not in dot and '"k1"' not in dot
    assert "->" not in dot  # both edges touched dropped nodes

    # only GROUNDS edges
    dot = build_dot(_sample_export(), edge_types={"GROUNDS"})
    assert '"GROUNDS"' in dot and '"RELATED_TO"' not in dot


def test_graph_export_is_read_only():
    """TC-GV-U3/U6: the export and DOT builder emit no mutating Cypher/ops."""
    from compendium.graph import browse
    from compendium.web import graphviz

    forbidden = ("CREATE", "MERGE", "DELETE", "SET ", "DETACH")
    export_src = inspect.getsource(browse.graph_export).upper()
    assert not any(f in export_src for f in forbidden), "graph_export must be read-only"
    dot_src = inspect.getsource(graphviz).upper()
    assert not any(f in dot_src for f in forbidden), "DOT builder must not mutate"


def test_graph_export_is_bounded():
    """TC-GV-U2: a full-graph export is capped and read-only (skips if down)."""
    from compendium.graph.client import graph_connection, graph_reachable
    from compendium.graph import browse

    with graph_connection() as driver:
        if not graph_reachable(driver):
            pytest.skip("Memgraph unreachable")
        before = browse.run_cypher(driver, "MATCH (n) RETURN count(n) AS c")[0]["c"]
        export = browse.graph_export(driver, limit=5)
        after = browse.run_cypher(driver, "MATCH (n) RETURN count(n) AS c")[0]["c"]

    assert len(export["nodes"]) <= 5  # bounded
    assert after == before  # read-only: export changed nothing
    for n in export["nodes"]:
        assert {"id", "label", "kind"} <= set(n)
