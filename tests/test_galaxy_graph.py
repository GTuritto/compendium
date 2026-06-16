"""Galaxy graph view (ADR-023, v0.6).

Hermetic: the semantic export runs against a stub Qdrant client (real cosine
similarity over tiny vectors); the read-only invariant is a source check.
"""

from __future__ import annotations

import inspect
import math


class _Point:
    def __init__(self, id, vector=None, payload=None, score=None):
        self.id = id
        self.vector = vector
        self.payload = payload
        self.score = score


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class StubQdrant:
    """Minimal Qdrant stand-in: retrieve / scroll / query_points, real cosine."""

    def __init__(self, pages):
        # pages: dict[id] -> (vector, payload)
        self.pages = pages

    def retrieve(self, collection_name, ids, with_vectors=False, with_payload=False):
        out = []
        for i in ids:
            if str(i) in self.pages:
                vec, pay = self.pages[str(i)]
                out.append(_Point(i, vector=vec if with_vectors else None,
                                  payload=pay if with_payload else None))
        return out

    def scroll(self, collection_name, limit, with_payload=False, **kw):
        pts = [_Point(i, payload=pay if with_payload else None)
               for i, (vec, pay) in self.pages.items()]
        return pts[:limit], None

    def query_points(self, collection_name, query, limit, with_payload=False, **kw):
        scored = [_Point(i, payload=pay, score=_cos(query, vec))
                  for i, (vec, pay) in self.pages.items()]
        scored.sort(key=lambda p: p.score, reverse=True)
        return type("R", (), {"points": scored[:limit]})()


def _pages():
    # Two tight clusters: {a,b,c} near each other, {d,e} near each other.
    return {
        "a": ([1.0, 0.0, 0.0], {"title": "Alpha", "slug": "alpha", "kind": "concept"}),
        "b": ([0.96, 0.1, 0.0], {"title": "Beta", "slug": "beta", "kind": "concept"}),
        "c": ([0.9, 0.2, 0.0], {"title": "Gamma", "slug": "gamma", "kind": "source"}),
        "d": ([0.0, 0.0, 1.0], {"title": "Delta", "slug": "delta", "kind": "concept"}),
        "e": ([0.05, 0.0, 0.97], {"title": "Epsilon", "slug": "epsilon", "kind": "topic"}),
    }


def test_full_graph_export_nodes_and_weighted_edges():
    """TC-GX-U1: bounded full-graph export -> nodes + similarity-weighted links."""
    from compendium.graph.semantic_export import semantic_graph_export

    g = semantic_graph_export(StubQdrant(_pages()), top_k=4, threshold=0.6)
    ids = {n["id"] for n in g["nodes"]}
    assert ids == {"a", "b", "c", "d", "e"}
    assert all({"id", "label", "kind"} <= set(n) for n in g["nodes"])
    # within-cluster pairs are linked; every link carries a weight
    pairs = {frozenset((e["source"], e["target"])) for e in g["links"]}
    assert frozenset(("a", "b")) in pairs
    assert all("weight" in e and 0.0 <= e["weight"] <= 1.0 for e in g["links"])
    # cross-cluster (a–d) is far below threshold, so not linked
    assert frozenset(("a", "d")) not in pairs


def test_threshold_filters_edges():
    """TC-GX-U2: raising the threshold yields fewer (stronger) edges."""
    from compendium.graph.semantic_export import semantic_graph_export

    loose = semantic_graph_export(StubQdrant(_pages()), top_k=4, threshold=0.5)
    strict = semantic_graph_export(StubQdrant(_pages()), top_k=4, threshold=0.99)
    assert len(strict["links"]) < len(loose["links"])


def test_export_is_bounded():
    """TC-GX-U3: the node count never exceeds the cap."""
    from compendium.graph.semantic_export import semantic_graph_export

    g = semantic_graph_export(StubQdrant(_pages()), limit=2)
    assert len(g["nodes"]) <= 2


def test_neighbourhood_export_includes_focus():
    """TC-GX-U1: a focus neighbourhood includes the focus and its neighbours."""
    from compendium.graph.semantic_export import semantic_graph_export

    g = semantic_graph_export(StubQdrant(_pages()), node_id="a", top_k=2, threshold=0.6)
    ids = {n["id"] for n in g["nodes"]}
    assert "a" in ids and "b" in ids  # focus + a close neighbour


def test_export_is_read_only():
    """TC-GX-U4: the export issues no mutating Cypher/Qdrant ops."""
    from compendium.graph import semantic_export

    src = inspect.getsource(semantic_export).upper()
    # Qdrant/Cypher mutators (as method calls / clauses, not English prose).
    forbidden = ("CREATE", "MERGE", "DETACH", ".UPSERT", ".DELETE", ".SET_PAYLOAD", ".OVERWRITE")
    assert not any(f in src for f in forbidden), "semantic export must be read-only"


# --- Nb: the pure HTML builder ----------------------------------------------

def _payload():
    return {
        "nodes": [
            {"id": "a", "label": "Alpha", "kind": "concept"},
            {"id": "b", "label": "Beta", "kind": "source"},
        ],
        "links": [{"source": "a", "target": "b", "weight": 0.82}],
    }


def test_build_galaxy_html_is_pure_and_inlines_payload_and_lib():
    """TC-GX-U5: payload + lib in -> deterministic self-contained HTML, no network."""
    from compendium.web.galaxy import build_galaxy_html

    lib = "/*VENDORED-FORCE-GRAPH*/window.ForceGraph3D=function(){};"
    html = build_galaxy_html(_payload(), lib)
    # deterministic
    assert html == build_galaxy_html(_payload(), lib)
    # the vendored lib is inlined, not referenced by URL
    assert "/*VENDORED-FORCE-GRAPH*/" in html
    assert "src=" not in html and "unpkg" not in html and "cdn" not in html.lower()
    # the data is embedded
    assert '"Alpha"' in html and '"weight": 0.82' in html


def test_build_galaxy_html_encodes_kind_color_and_weight():
    """TC-GX-U6: nodes coloured by kind, sized by degree; links use weight."""
    from compendium.web.galaxy import KIND_COLOR, build_galaxy_html

    html = build_galaxy_html(_payload(), "x")
    assert KIND_COLOR["concept"] in html and KIND_COLOR["source"] in html
    assert "nodeVal" in html and "linkWidth" in html  # degree size + weight width


def test_vendored_asset_present_and_not_cdn():
    """TC-GX-U8: the renderer loads from the vendored asset, not a CDN."""
    from compendium.web import galaxy

    lib = galaxy.load_lib()
    assert "ForceGraph3D" in lib  # the real vendored bundle
    builder_src = inspect.getsource(galaxy)
    assert "unpkg" not in builder_src and "https://" not in builder_src
