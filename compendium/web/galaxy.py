"""Pure HTML builder for the WebUI 3D galaxy view (ADR-023).

No Streamlit, no network: a ``{nodes, links}`` payload (from
``graph/semantic_export.py``) plus the vendored ``3d-force-graph`` JS in, a
self-contained HTML string out for ``st.components.v1.html``. The renderer JS is
**vendored** (``compendium/web/static/3d-force-graph.min.js``) and inlined, so the
loopback WebUI needs no CDN. ``build_galaxy_html`` is a pure function (the JS is
passed in) so it stays hermetically testable; ``load_lib`` does the one file read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LIB_PATH = Path(__file__).resolve().parent / "static" / "3d-force-graph.min.js"

# On-brand kind colours, keyed lowercase (Qdrant page kinds are lowercase;
# matches compendium/web/graphviz.py _KIND_COLOR).
KIND_COLOR = {
    "source": "#9aa7ff",
    "concept": "#5fcf97",
    "topic": "#ffb45f",
    "chunk": "#cfd3d6",
}


def load_lib() -> str:
    """Read the vendored 3d-force-graph bundle (the one I/O at the edge)."""
    return _LIB_PATH.read_text(encoding="utf-8")


def build_galaxy_html(
    payload: dict[str, Any],
    lib_js: str,
    *,
    height: int = 620,
    kind_color: dict[str, str] | None = None,
) -> str:
    """A self-contained 3D-galaxy HTML document for ``st.components.v1.html``.

    ``payload`` is ``{"nodes": [{id,label,kind}], "links": [{source,target,weight}]}``.
    ``lib_js`` is the vendored 3d-force-graph source (inlined — no external src).
    Nodes are coloured by kind, sized by degree; links are widthed by similarity
    weight. Read-only: hover labels, orbit/zoom/drag, gentle auto-orbit. Pure.
    """
    colors = kind_color or KIND_COLOR
    data_json = json.dumps(payload)
    color_json = json.dumps(colors)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; background: #05060f; overflow: hidden; }}
  #graph {{ width: 100%; height: {height}px; }}
</style></head><body>
<div id="graph"></div>
<script>{lib_js}</script>
<script>
  const DATA = {data_json};
  const COLOR = {color_json};
  const deg = {{}};
  DATA.links.forEach(l => {{ deg[l.source]=(deg[l.source]||0)+1; deg[l.target]=(deg[l.target]||0)+1; }});
  DATA.nodes.forEach(n => n.val = 1 + (deg[n.id]||0));
  const elem = document.getElementById('graph');
  const Graph = ForceGraph3D()(elem)
    .backgroundColor('#05060f')
    .graphData(DATA)
    .nodeLabel(n => `${{n.label}}  ·  ${{n.kind}}`)
    .nodeColor(n => COLOR[(n.kind||'').toLowerCase()] || '#dddddd')
    .nodeVal('val')
    .nodeOpacity(0.92)
    .linkColor(() => 'rgba(150,170,210,0.35)')
    .linkWidth(l => (l.weight||0.5) * 1.6)
    .linkOpacity(0.5);
  Graph.d3Force('charge').strength(-55);
  let angle = 0, auto = true, dist = 320;
  elem.addEventListener('pointerdown', () => auto = false);
  setInterval(() => {{
    if (!auto) return;
    Graph.cameraPosition({{ x: dist*Math.sin(angle), z: dist*Math.cos(angle) }});
    angle += Math.PI / 600;
  }}, 30);
</script>
</body></html>"""
