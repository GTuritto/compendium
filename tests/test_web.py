"""The web UI (ADR-015): the launcher contract and headless view smokes.

The AppTest smokes drive the real Streamlit script with the facade and the
curation provider monkeypatched — hermetic, no stores, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


# --- the launcher ------------------------------------------------------------


def test_streamlit_argv_is_loopback_by_default():
    from compendium.web import streamlit_argv

    argv = streamlit_argv()
    assert argv[1:4] == ["-m", "streamlit", "run"]
    assert argv[4].endswith("compendium/web/app.py")
    assert argv[argv.index("--server.address") + 1] == "127.0.0.1"
    assert argv[argv.index("--server.port") + 1] == "8501"
    assert "--server.headless" in argv


def test_run_propagates_streamlit_exit_code(monkeypatch):
    import subprocess

    from compendium import web

    seen = {}

    def fake_run(argv):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, returncode=7)

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    assert web.run(host="127.0.0.1", port=9000) == 7
    assert seen["argv"][seen["argv"].index("--server.port") + 1] == "9000"


# --- AppTest view smokes -------------------------------------------------------


@dataclass
class _Citation:
    ref: int = 1
    slug: str = "psychological-safety"
    title: str = "psychological safety"
    trace_rank: int = 1


@dataclass
class _AskResult:
    answer: str | None = "A grounded answer."
    refused: bool = False
    citations: list = field(default_factory=lambda: [_Citation()])
    coverage_score: float = 0.91
    trace_id: str = "trace-1"
    ask_trace_id: str = "ask-1"
    gap: dict | None = None
    suggested_actions: list = field(default_factory=list)


@dataclass
class _Page:
    title: str = "psychological safety"
    slug: str = "psychological-safety"
    kind: str = "concept"
    status: str = "canonical"
    score: float = 0.0321


@dataclass
class _QueryResult:
    pages: list = field(default_factory=lambda: [_Page()])
    coverage_score: float = 0.77
    fallback_to_chunks: bool = False
    citations: list = field(default_factory=list)


def _app():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app = Path(__file__).resolve().parents[1] / "compendium" / "web" / "app.py"
    return AppTest.from_file(str(app), default_timeout=30)


@pytest.fixture
def fake_surface(monkeypatch):
    from compendium.api import facade
    from compendium.tui import data as provider

    calls: dict = {"resolved": []}
    monkeypatch.setattr(facade, "ask", lambda q, **k: _AskResult())
    monkeypatch.setattr(facade, "query", lambda t, **k: _QueryResult())
    monkeypatch.setattr(facade, "page_list", lambda **k: [
        {"kind": "concept", "slug": "psychological-safety", "title": "psychological safety", "status": "canonical"}
    ])
    monkeypatch.setattr(facade, "page_get", lambda kind, slug: {
        "kind": kind, "slug": slug, "title": "psychological safety",
        "status": "canonical", "aliases": [], "file_path": "x.md", "markdown": "# PS\n\nBody.",
    })
    monkeypatch.setattr(provider, "curation_signals", lambda: [{
        "id": "sig-1", "kind": "contradiction_candidate", "priority": 15,
        "payload": {
            "from_slug": "a", "from_title": "A", "from_kind": "concept",
            "to_slug": "b", "to_title": "B", "to_kind": "concept",
            "confidence": 0.9, "rationale": "claims differ",
        },
        "created_at": None,
    }])
    monkeypatch.setattr(
        provider, "resolve_signal",
        lambda sid, *, approve: calls["resolved"].append((sid, approve)) or "done",
    )
    return calls


def test_ask_view_renders_answer_and_citations(fake_surface):
    at = _app().run()
    at.text_input(key="ask_question").set_value("What is psychological safety?")
    at.button(key="ask_go").click()
    at.run()
    body = " ".join(m.value for m in at.markdown)
    assert "A grounded answer." in body
    assert "psychological-safety" in body
    assert not at.exception


def test_search_view_renders_ranked_pages(fake_surface):
    at = _app().run()
    at.sidebar.radio(key="view").set_value("Search")
    at.run()
    at.text_input(key="search_text").set_value("psychological safety")
    at.button(key="search_go").click()
    at.run()
    body = " ".join(m.value for m in at.markdown)
    assert "concept/psychological-safety" in body
    assert not at.exception


def test_pages_view_renders_markdown_body(fake_surface):
    at = _app().run()
    at.sidebar.radio(key="view").set_value("Pages")
    at.run()
    body = " ".join(m.value for m in at.markdown)
    assert "Body." in body
    assert not at.exception


def test_curation_view_approve_runs_the_resolve_action(fake_surface):
    at = _app().run()
    at.sidebar.radio(key="view").set_value("Curation")
    at.run()
    at.button(key="approve-sig-1").click()
    at.run()
    assert fake_surface["resolved"] == [("sig-1", True)]
    assert not at.exception
