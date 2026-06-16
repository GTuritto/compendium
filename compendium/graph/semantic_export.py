"""Semantic-similarity graph export for the WebUI galaxy view (ADR-023).

A sibling to ``graph/browse.py:graph_export`` (which emits Memgraph *typed*
edges). This builds a ``{nodes, links}`` payload from **Qdrant nearest-
neighbours**: each page's top-K neighbours become undirected, similarity-
weighted edges, kept only at or above a threshold. It reuses the edge-extractor's
``nearest_neighbours`` helper (ADR-010) so the similarity signal is defined once.

Read-only by construction: it only reads from Qdrant (``retrieve`` / ``scroll`` /
``query_points``) and never writes. Bounded by a node cap so a large corpus stays
renderable.
"""

from __future__ import annotations

from typing import Any

from compendium.curate.extract import Neighbour, nearest_neighbours
from compendium.index.qdrant import PAGES_COLLECTION

DEFAULT_TOP_K = 8
DEFAULT_THRESHOLD = 0.6
DEFAULT_LIMIT = 300
_MAX_LIMIT = 2000
_MAX_TOP_K = 50


def _node_from_payload(entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity_id,
        "label": payload.get("title") or payload.get("slug") or entity_id,
        "kind": payload.get("kind") or "?",
    }


def _node_from_neighbour(nb: Neighbour) -> dict[str, Any]:
    return {"id": nb.entity_id, "label": nb.title or nb.slug or nb.entity_id, "kind": nb.kind or "?"}


def semantic_graph_export(
    qclient: Any,
    *,
    node_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """A bounded, read-only ``{nodes, links}`` similarity graph from Qdrant kNN.

    ``node_id`` gives a page's neighbourhood (the focus plus its top-K neighbours);
    otherwise a bounded full-graph sample (the first ``limit`` page points). Edges
    connect node pairs whose vector similarity is ``>= threshold``; each link
    carries that similarity as ``weight``. ``limit`` caps the node count (hard max
    2000). Never mutates any store.
    """
    limit = max(1, min(int(limit), _MAX_LIMIT))
    top_k = max(1, min(int(top_k), _MAX_TOP_K))

    nodes: dict[str, dict[str, Any]] = {}
    if node_id:
        focus = qclient.retrieve(
            collection_name=PAGES_COLLECTION, ids=[node_id], with_payload=True
        )
        if focus:
            nodes[str(node_id)] = _node_from_payload(str(node_id), focus[0].payload or {})
        for nb in nearest_neighbours(qclient, node_id, top_k):
            nodes.setdefault(nb.entity_id, _node_from_neighbour(nb))
    else:
        points, _ = qclient.scroll(
            collection_name=PAGES_COLLECTION, limit=limit, with_payload=True
        )
        for p in points:
            nodes.setdefault(str(p.id), _node_from_payload(str(p.id), p.payload or {}))

    # Cap the node set deterministically before drawing edges.
    if len(nodes) > limit:
        keep = set(list(nodes)[:limit])
        nodes = {nid: n for nid, n in nodes.items() if nid in keep}

    # Edges: each node's neighbours that are also in the node set and at/above
    # the similarity threshold. Undirected, deduped by unordered pair.
    seen: set[frozenset[str]] = set()
    links: list[dict[str, Any]] = []
    for nid in list(nodes):
        for nb in nearest_neighbours(qclient, nid, top_k):
            if nb.entity_id not in nodes or nb.score < threshold:
                continue
            pair = frozenset((nid, nb.entity_id))
            if len(pair) < 2 or pair in seen:
                continue
            seen.add(pair)
            links.append(
                {"source": nid, "target": nb.entity_id, "weight": round(float(nb.score), 3)}
            )

    return {"nodes": list(nodes.values()), "links": links}
