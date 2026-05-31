"""v0.2 Phase 7 — HTTP transport tests (7b).

A unit check of the route set and the loopback default runs anywhere. The verb
round-trips run against a migrated ``compendium_test`` database plus running
OpenSearch and Qdrant, with the stub embedder and synthesizer; they skip when a
store is unreachable.
"""

from __future__ import annotations

import base64
import inspect
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


# --- unit: routes + loopback default (no stores) ---------------------------


def test_app_exposes_the_six_verbs_and_run_binds_loopback():
    from compendium.api.http import create_app, run

    app = create_app()
    paths = {route.path for route in app.routes}
    assert {"/query", "/ask", "/ask/stream", "/ingest", "/page_get", "/page_list", "/index_status"} <= paths
    assert inspect.signature(run).parameters["host"].default == "127.0.0.1"
    assert inspect.signature(run).parameters["port"].default == 8787


# --- integration: verb round-trips -----------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A TestClient over a seeded corpus, with stub embedder + synthesizer."""
    from fastapi.testclient import TestClient

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

    from compendium.api.http import create_app
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest as _ingest

    _ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")
    yield TestClient(create_app())
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


@pytest.mark.integration
def test_http_index_status_and_query(client):
    r = client.get("/index_status")
    assert r.status_code == 200
    body = r.json()
    assert "opensearch" in body and "qdrant" in body

    r = client.post("/query", json={"text": "psychological safety team learning"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["pages"]
    assert "coverage_score" in payload

    assert client.post("/query", json={}).status_code == 400


@pytest.mark.integration
def test_http_ask_buffered_and_streaming(client):
    r = client.post("/ask", json={"question": "What is psychological safety?"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["refused"] is False
    assert payload["answer"]
    assert payload["citations"] and payload["citations"][0]["ref"] == "[1]"
    assert payload["ask_trace_id"]

    r = client.post("/ask/stream", json={"question": "What is psychological safety?"})
    assert r.status_code == 200
    text = r.text
    final = json.loads(text.rstrip().splitlines()[-1])  # last line is the JSON envelope
    assert final["answer"]
    assert "citations" in final and "coverage_score" in final and final["ask_trace_id"]
    assert text[: text.rfind("\n")].strip()  # answer streamed before the envelope


@pytest.mark.integration
def test_http_ingest_bytes_autosyncs_and_pages(client):
    note = b"# Spaced Repetition\n\nSpaced repetition schedules reviews at increasing intervals to fight forgetting.\n"
    r = client.post(
        "/ingest",
        json={
            "kind": "note",
            "filename": "spaced-repetition.md",
            "content_base64": base64.b64encode(note).decode(),
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] in ("ingested", "updated", "unchanged")

    # auto-synced -> queryable
    r = client.post("/query", json={"text": "spaced repetition reviews intervals forgetting"})
    assert r.status_code == 200 and r.json()["pages"]

    # page_list / page_get
    pages = client.get("/page_list", params={"kind": "source"}).json()
    assert pages
    slug = pages[0]["slug"]
    got = client.get("/page_get", params={"kind": "source", "slug": slug})
    assert got.status_code == 200 and got.json()["markdown"]
    assert client.get("/page_get", params={"kind": "concept", "slug": "nope-xyz"}).status_code == 404
