"""Phase 8 ops-console tests.

Data-provider unit tests and Textual Pilot tests over a seeded corpus. Both need
a migrated ``compendium_test`` database; the Pilot session also needs OpenSearch,
Qdrant, and Memgraph. They skip if a required store is unreachable and use the
deterministic synth/embed stubs. Async bodies are driven via ``asyncio.run`` so
no extra pytest plugin is required.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def tui_env(monkeypatch, tmp_path):
    """A seeded corpus (source + concept + indexes + graph + one query) and env
    pointed at it. Skips if any backing store is unreachable."""
    from compendium.graph.client import graph_driver, graph_reachable
    from compendium.index.clients import (
        opensearch_client, opensearch_reachable, qdrant_client, qdrant_reachable,
    )

    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    if not opensearch_reachable(opensearch_client()):
        pytest.skip("OpenSearch unreachable")
    if not qdrant_reachable(qdrant_client()):
        pytest.skip("Qdrant unreachable")
    gd = graph_driver()
    if not graph_reachable(gd):
        gd.close()
        pytest.skip("Memgraph unreachable")
    gd.close()

    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")

    vault = tmp_path / "vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True)

    monkeypatch.setenv("POSTGRES_URL", test_url)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("COMPENDIUM_EMBED_STUB", "1")
    monkeypatch.setenv("COMPENDIUM_SYNTH_STUB", "1")

    from compendium.db.connection import connection
    from compendium.graph.rebuild import rebuild
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest
    from compendium.retrieve.pipeline import query as run_query
    from compendium.wiki.synth import synthesize_concept

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    with connection() as conn:
        synthesize_concept(conn, "psychological safety", aliases=[], vault_path=str(vault))
    reindex("all")
    rebuild()
    run_query("psychological safety team learning")

    yield test_url

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


# --- data providers --------------------------------------------------------


def test_data_providers_shapes(tui_env):
    from compendium.tui import data as tui_data

    dash = tui_data.dashboard()
    assert set(dash) == {"counts", "sync_lag", "recent_traces"}
    assert dash["counts"]["sources"] >= 1 and dash["counts"]["query_traces"] >= 1
    assert tui_data.sources(), "expected at least one source"
    assert any(p["kind"] == "concept" for p in tui_data.pages())
    assert tui_data.pages(kind="source"), "kind filter should match source pages"
    assert tui_data.curation_signals() == []  # empty until Phase 9


# --- Pilot: reachability + bindings ----------------------------------------


def test_app_boots_and_screens_reachable(tui_env):
    from compendium.tui.app import CompendiumTUI, HelpScreen
    from compendium.tui.screens.curation import CurationScreen
    from compendium.tui.screens.dashboard import DashboardScreen
    from compendium.tui.screens.graph import GraphScreen
    from compendium.tui.screens.pages import PagesScreen
    from compendium.tui.screens.sources import SourcesScreen
    from compendium.tui.screens.workbench import WorkbenchScreen

    expected = {
        "d": DashboardScreen, "s": SourcesScreen, "p": PagesScreen,
        "w": WorkbenchScreen, "c": CurationScreen, "g": GraphScreen,
    }

    async def body():
        app = CompendiumTUI()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DashboardScreen)
            for key, screen_cls in expected.items():
                await pilot.press(key)
                await pilot.pause()
                assert isinstance(app.screen, screen_cls), (key, type(app.screen))
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(body())


# --- Pilot: the keyboard-only daily-use session ----------------------------


def test_keyboard_session(tui_env):
    from textual.widgets import DataTable, Input, Static

    from compendium.tui.app import CompendiumTUI
    from compendium.tui.screens.graph import GraphScreen
    from compendium.tui.screens.sources import SourcesScreen
    from compendium.tui.screens.widgets import FormModal
    from compendium.tui.screens.workbench import WorkbenchScreen

    async def body():
        app = CompendiumTUI()
        async with app.run_test() as pilot:
            # ingest a source (re-ingest the fixture -> unchanged, but exercises the path)
            await pilot.press("s"); await pilot.pause()
            assert isinstance(app.screen, SourcesScreen)
            await app.workers.wait_for_complete(); await pilot.pause()
            await pilot.press("i"); await pilot.pause()
            assert isinstance(app.screen, FormModal)
            app.screen.query_one("#f_path", Input).value = str(_FIXTURES / "sample.md")
            app.screen.query_one("#f_kind", Input).value = "note"
            await pilot.press("enter"); await pilot.pause()
            await app.workers.wait_for_complete(); await pilot.pause()
            assert isinstance(app.screen, SourcesScreen)

            # run a synth
            await pilot.press("p"); await pilot.pause()
            await pilot.press("y"); await pilot.pause()
            assert isinstance(app.screen, FormModal)
            app.screen.query_one("#f_kind", Input).value = "concept"
            app.screen.query_one("#f_name", Input).value = "team learning"
            await pilot.press("enter"); await pilot.pause()
            await app.workers.wait_for_complete(); await pilot.pause()

            # run a workbench query (/ focuses the query box)
            await pilot.press("w"); await pilot.pause()
            assert isinstance(app.screen, WorkbenchScreen)
            await pilot.press("slash"); await pilot.pause()
            app.screen.query_one("#q", Input).value = "psychological safety"
            await pilot.press("enter"); await pilot.pause()
            await app.workers.wait_for_complete(); await pilot.pause()
            assert app.screen.query_one("#results", DataTable).row_count >= 1

            # browse the graph (/ focuses the search box)
            await pilot.press("g"); await pilot.pause()
            assert isinstance(app.screen, GraphScreen)
            await pilot.press("slash"); await pilot.pause()
            app.screen.query_one("#q", Input).value = "Sample"
            await pilot.press("enter"); await pilot.pause()
            await app.workers.wait_for_complete(); await pilot.pause()
            await pilot.press("enter"); await pilot.pause()  # select first node -> walk
            await app.workers.wait_for_complete(); await pilot.pause()
            assert app.screen.query_one("#edges", DataTable).row_count >= 1

    asyncio.run(body())
