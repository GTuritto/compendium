"""The Streamlit app: ask / search / browse / curate in the browser (ADR-015).

A thin front-end over the existing seams and nothing else: Ask, Search, and
Pages call ``compendium/api/facade.py`` (the same six-verb facade the HTTP and
MCP transports share); Curation drains the queue through the ``tui/data.py``
provider — including the ADR-014 ``contradiction_candidate`` signals, whose
Approve / Drop buttons run the same Phase 1 resolve action as the CLI and TUI.
No retrieval, answer, compose, or curation logic lives here.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from compendium import __version__
from compendium.api import facade
from compendium.tui import data as provider

_LOGO = Path(__file__).resolve().parent / "logo.png"

st.set_page_config(page_title="Compendium", page_icon=str(_LOGO), layout="wide")

VIEWS = ("Ask", "Search", "Pages", "Curation", "Graph", "Dashboard")

st.sidebar.image(str(_LOGO), width=140)
st.sidebar.title("Compendium")
st.sidebar.caption(f"v{__version__} · loopback only (ADR-015)")
view = st.sidebar.radio("View", VIEWS, key="view")


# --- Dashboard ---------------------------------------------------------------
# Counts/health + NON-DESTRUCTIVE ops only (ADR-020): reindex, graph rebuild,
# and inbox "process now" rebuild/recover from the canonical layer. Destructive
# ops (delete, wipe, restore) and unit management stay TUI/CLI only and are
# deliberately absent here.

if view == "Dashboard":
    st.header("Dashboard")
    status = facade.index_status()
    data = provider.dashboard()

    st.subheader("Counts")
    counts = data["counts"]
    cols = st.columns(len(counts) or 1)
    for col, (name, n) in zip(cols, counts.items()):
        col.metric(name, n)

    st.subheader("Derived indexes")
    st.json({"opensearch": status.opensearch, "qdrant": status.qdrant})
    if status.sync_lag:
        st.caption("Sync lag")
        st.table(status.sync_lag)

    st.subheader("Maintenance (non-destructive)")
    c1, c2, c3 = st.columns(3)
    if c1.button("Reindex all", key="adm_reindex"):
        with st.spinner("Reindexing…"):
            rep = provider.reindex_all()
        st.success(f"reindexed {rep.indexed}, failed {rep.failed}")
    if c2.button("Rebuild graph", key="adm_graph"):
        with st.spinner("Rebuilding graph…"):
            provider.graph_rebuild()
        st.success("graph rebuilt from PostgreSQL + the vault")
    if c3.button("Process inbox now", key="adm_inbox"):
        with st.spinner("Processing inbox…"):
            rep = provider.process_inbox()
        st.success(
            f"processed {getattr(rep, 'processed', 0)}, "
            f"failed {getattr(rep, 'failed', 0)}"
        )
    st.caption(
        "Destructive ops (delete, wipe, restore) and unit management are "
        "TUI/CLI only — ADR-020."
    )


# --- Ask ---------------------------------------------------------------------

elif view == "Ask":
    st.header("Ask")
    question = st.text_input("Question", key="ask_question")
    if st.button("Ask", key="ask_go") and question.strip():
        with st.spinner("Composing over the wiki…"):
            result = facade.ask(question.strip())
        if result.refused:
            st.warning("Refused: retrieval coverage is below the threshold.")
            if result.gap:
                st.json(result.gap)
            if result.suggested_actions:
                st.subheader("Suggested actions")
                for action in result.suggested_actions:
                    st.code(action, language="bash")
        else:
            st.markdown(result.answer)
            if result.citations:
                st.subheader("Citations")
                for c in result.citations:
                    st.markdown(f"**[{c.ref}]** {c.title} (`{c.slug}`) — trace rank {c.trace_rank}")
        st.caption(
            f"coverage {result.coverage_score:.3f} · trace {result.trace_id} · "
            f"ask trace {result.ask_trace_id}"
        )


# --- Search --------------------------------------------------------------------

elif view == "Search":
    st.header("Search")
    text = st.text_input("Query", key="search_text")
    if st.button("Search", key="search_go") and text.strip():
        with st.spinner("Page-first retrieval…"):
            result = facade.query(text.strip())
        fallback = " · chunk fallback" if result.fallback_to_chunks else ""
        st.caption(f"coverage {result.coverage_score:.3f}{fallback}")
        for i, page in enumerate(result.pages, start=1):
            st.markdown(
                f"**{i}. {page.title}** (`{page.kind}/{page.slug}`)"
                f"{' · draft' if page.status == 'draft' else ''} — score {page.score:.5f}"
            )
        if result.fallback_to_chunks and result.citations:
            st.subheader("Citations (chunk fallback)")
            for c in result.citations:
                st.markdown(f"- *{c.source_title}* #{c.position}: {c.preview}")


# --- Pages ---------------------------------------------------------------------

elif view == "Pages":
    st.header("Pages")
    kind = st.selectbox("Kind", ("concept", "topic", "source"), key="pages_kind")
    rows = facade.page_list(kind=kind)
    if not rows:
        st.info("No pages of this kind yet.")
    else:
        labels = {f"{r['title']} ({r['slug']})": r for r in rows}
        choice = st.selectbox("Page", list(labels), key="pages_slug")
        row = labels[choice]
        page = facade.page_get(row["kind"], row["slug"])
        if page is None:
            st.error("Page not found.")  # the facade's one not-found decision
        else:
            with st.expander("Frontmatter"):
                st.json({k: v for k, v in page.items() if k != "markdown"})
            st.markdown(page["markdown"] or "*(no vault body)*")


# --- Curation --------------------------------------------------------------------

elif view == "Curation":
    st.header("Curation queue")
    signals = provider.curation_signals()
    if not signals:
        st.success("No open signals.")
    for s in signals:
        sid = str(s["id"])
        payload = s["payload"] or {}
        with st.container(border=True):
            st.markdown(f"**{s['kind']}** · priority {s['priority']} · `{sid}`")
            if s["kind"] == "contradiction_candidate":
                st.markdown(
                    f"*{payload.get('from_title')}* (`{payload.get('from_slug')}`) "
                    f"⇄ *{payload.get('to_title')}* (`{payload.get('to_slug')}`)"
                )
                st.markdown(
                    f"confidence **{payload.get('confidence')}** — {payload.get('rationale', '')}"
                )
                col_a, col_b = st.columns(2)
                if col_a.button("Approve → CONTRADICTS edge", key=f"approve-{sid}"):
                    st.toast(provider.resolve_signal(sid, approve=True))
                    st.rerun()
                if col_b.button("Drop", key=f"drop-{sid}"):
                    st.toast(provider.resolve_signal(sid, approve=False))
                    st.rerun()
            else:
                st.json(payload)
                col_a, col_b = st.columns(2)
                if col_a.button("Synth a draft page", key=f"synth-{sid}"):
                    with st.spinner("Synthesizing…"):
                        slug = provider.synth_signal(sid)
                    st.toast(f"drafted '{slug}'")
                    st.rerun()
                if col_b.button("Drop", key=f"drop-{sid}"):
                    st.toast(provider.resolve_signal(sid, approve=False))
                    st.rerun()


# --- Graph -------------------------------------------------------------------
# Read-only, bounded views of the knowledge graph. Two renderers: the ADR-021
# graphviz map over Memgraph's typed edges (the no-JS fallback), and the ADR-023
# interactive 3D galaxy over Qdrant semantic similarity (vendored 3d-force-graph,
# no pip dependency). Both read-only; fits the WebUI safe-only posture (ADR-020).

elif view == "Graph":
    import streamlit.components.v1 as components

    from compendium.web.galaxy import build_galaxy_html, filter_by_kind, load_lib
    from compendium.web.graphviz import build_dot

    _NODE_KINDS = ["Source", "Concept", "Topic", "Chunk"]
    _EDGE_TYPES = [
        "PART_OF", "EVIDENCES", "GROUNDS", "RELATED_TO",
        "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS",
    ]
    _GX_KINDS = ["concept", "source", "topic", "chunk"]

    st.header("Graph")
    renderer = st.radio(
        "Renderer", ("2D graphviz (typed edges)", "3D galaxy (semantic similarity)"),
        key="gv_renderer", horizontal=True,
    )
    mode = st.radio(
        "Scope", ("Neighbourhood", "Full graph (sampled)"),
        key="gv_mode", horizontal=True,
    )

    # Shared focus search (title/slug -> node id; page ids match Qdrant points).
    node_id: str | None = None
    if mode == "Neighbourhood":
        term = st.text_input("Find a focus node (title/slug)", key="gv_term")
        if term.strip():
            try:
                matches = provider.graph_search(term.strip())
            except provider.GraphUnreachable:
                matches = []
                st.error("Memgraph unreachable (focus search). Try Full graph.")
            if matches:
                labels = [f"{m['label']} ({m['kind']})" for m in matches]
                pick = st.selectbox("Focus node", labels, key="gv_focus")
                node_id = matches[labels.index(pick)]["id"]
                st.caption(f"Focused on `{node_id}` — select another to re-center.")
            elif term.strip():
                st.info("No matching node.")

    draw = mode == "Full graph (sampled)" or node_id

    if draw and renderer.startswith("2D"):
        kinds = st.multiselect(
            "Node kinds", _NODE_KINDS, default=["Source", "Concept", "Topic"], key="gv_kinds"
        )
        edge_types = st.multiselect("Edge types", _EDGE_TYPES, key="gv_edges")
        try:
            export = provider.graph_export(node_id=node_id)
        except provider.GraphUnreachable:
            st.error("Memgraph unreachable.")
            export = None
        if export is not None:
            dot = build_dot(export, kinds=set(kinds) or None, edge_types=set(edge_types) or None)
            st.caption(
                f"{len(export['nodes'])} nodes · {len(export['edges'])} edges "
                "(typed, bounded, read-only)"
            )
            st.graphviz_chart(dot)

    elif draw:  # 3D galaxy
        c1, c2, c3 = st.columns(3)
        threshold = c1.slider("Similarity threshold", 0.30, 0.95, 0.60, 0.05, key="gx_thr")
        top_k = c2.slider("Neighbours per node", 3, 20, 8, key="gx_k")
        cap = c3.slider("Node cap", 50, 500, 300, 50, key="gx_cap")
        gx_kinds = st.multiselect(
            "Node kinds", _GX_KINDS, default=["concept", "source", "topic"], key="gx_kinds"
        )
        try:
            galaxy = provider.semantic_graph(
                node_id=node_id, top_k=top_k, threshold=threshold, limit=cap
            )
        except provider.GraphUnreachable:
            st.error("Qdrant unreachable.")
            galaxy = None
        if galaxy is not None:
            galaxy = filter_by_kind(galaxy, gx_kinds)
            st.caption(
                f"{len(galaxy['nodes'])} nodes · {len(galaxy['links'])} edges "
                "(semantic similarity, bounded, read-only) · drag to orbit, scroll to zoom"
            )
            components.html(build_galaxy_html(galaxy, load_lib()), height=660)
