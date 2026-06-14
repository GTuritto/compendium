"""v0.2 Phase 7 — MCP transport tests (7c).

A static ``list_tools`` check (the six verbs + input schemas) runs anywhere.
``call_tool`` round-trips run against a migrated ``compendium_test`` database
plus running OpenSearch and Qdrant, with the stub embedder and synthesizer; they
skip when a store is unreachable.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


def _payload(call_result):
    """Extract the JSON payload from a FastMCP call_tool result.

    ``call_tool`` returns ``(content_blocks, structured)``; our tools return a
    JSON string, so the first text block carries the payload.
    """
    content, _structured = call_result
    return json.loads(content[0].text)


# --- unit: the six tools and their input schemas ---------------------------


def test_mcp_lists_the_six_verbs_with_schemas():
    from compendium.api.mcp import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "query", "ask", "ingest", "page_get", "page_list", "index_status",
        # v0.5 agent object store (ADR-017)
        "object_put", "object_get", "object_list", "object_delete", "object_promote",
    }

    by_name = {t.name: t for t in tools}
    assert "text" in by_name["query"].inputSchema["properties"]
    # the injected Context param is not part of the ask tool's input schema
    ask_props = by_name["ask"].inputSchema["properties"]
    assert "question" in ask_props and "ctx" not in ask_props
    assert "kind" in by_name["ingest"].inputSchema["properties"]


# --- integration: invoking the tools ---------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def server(monkeypatch, tmp_path):
    """A FastMCP server over a seeded corpus, with stub embedder + synthesizer."""
    from compendium.index.clients import (
        opensearch_client,
        opensearch_reachable,
        qdrant_client,
        qdrant_reachable,
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

    from compendium.api.mcp import build_server
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest as _ingest

    _ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")
    yield build_server()
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


@pytest.mark.integration
def test_mcp_query_and_index_status(server):
    async def run():
        q = _payload(await server.call_tool("query", {"text": "psychological safety team learning"}))
        st = _payload(await server.call_tool("index_status", {}))
        return q, st

    query_payload, status_payload = asyncio.run(run())
    assert query_payload["pages"]
    assert "coverage_score" in query_payload
    assert "opensearch" in status_payload and "qdrant" in status_payload


@pytest.mark.integration
def test_mcp_ask_returns_answer_with_citations(server):
    async def run():
        return _payload(await server.call_tool("ask", {"question": "What is psychological safety?"}))

    payload = asyncio.run(run())
    assert payload["refused"] is False
    assert payload["answer"]
    assert payload["citations"] and payload["citations"][0]["ref"] == "[1]"
    assert payload["ask_trace_id"]
