"""The Streamlit app: ask / search / browse / curate in the browser (ADR-015).

A thin front-end over the existing seams and nothing else: Ask, Search, and
Pages call ``compendium/api/facade.py`` (the same six-verb facade the HTTP and
MCP transports share); Curation drains the queue through the ``tui/data.py``
provider — including the ADR-014 ``contradiction_candidate`` signals, whose
Approve / Drop buttons run the same Phase 1 resolve action as the CLI and TUI.
No retrieval, answer, compose, or curation logic lives here.
"""

from __future__ import annotations

import streamlit as st

from compendium import __version__
from compendium.api import facade
from compendium.tui import data as provider

st.set_page_config(page_title="Compendium", layout="wide")

VIEWS = ("Ask", "Search", "Pages", "Curation")

st.sidebar.title("Compendium")
st.sidebar.caption(f"v{__version__} · loopback only (ADR-015)")
view = st.sidebar.radio("View", VIEWS, key="view")


# --- Ask ---------------------------------------------------------------------

if view == "Ask":
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
