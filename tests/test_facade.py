"""v0.2 Phase 7 — access-surface facade tests (7a).

Unit tests (the shared serializer, raw-bytes ingest via monkeypatch, the
argument guard) run anywhere. Integration tests exercise the read verbs and the
auto-sync ingest against a migrated ``compendium_test`` database plus running
OpenSearch and Qdrant; they skip when a store is unreachable and use the stub
embedder.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit: the shared serializer -------------------------------------------


def test_to_payload_matches_render_json():
    import json

    from compendium.api import to_payload
    from compendium.cli import render
    from compendium.retrieve.pipeline import PageResult, RetrievalResult

    result = RetrievalResult(
        query_text="q",
        pages=[PageResult("A", "Alpha", "a", "concept", "canonical", 1.0, {})],
        coverage_score=0.5,
        fallback_to_chunks=False,
        citations=[],
        gaps=[],
        trace={},
    )
    payload = to_payload(result)
    assert payload == json.loads(render.to_json(result))
    assert payload["query_text"] == "q"
    assert payload["coverage_score"] == 0.5
    assert payload["pages"][0]["slug"] == "a"


# --- unit: ingest raw bytes (monkeypatched core + sync) --------------------


def test_ingest_raw_bytes_writes_temp_ingests_and_autosyncs(monkeypatch):
    import compendium.index.sync as sync_mod
    import compendium.ingest.pipeline as ingest_mod
    from compendium.index.sync import SyncReport
    from compendium.ingest.pipeline import IngestResult

    seen: dict = {}

    def fake_ingest(path, *, kind, mine=False):
        p = Path(path)
        seen["path"] = path
        seen["existed"] = p.is_file()
        seen["content"] = p.read_bytes()
        seen["kind"] = kind
        return [IngestResult(path, "ingested", UUID(int=1), 3, "")]

    calls = {"sync": 0}

    def fake_sync(*a, **k):
        calls["sync"] += 1
        return SyncReport(indexed=0, failed=0, skipped=0)

    monkeypatch.setattr(ingest_mod, "ingest", fake_ingest)
    monkeypatch.setattr(sync_mod, "sync_pending", fake_sync)

    from compendium.api import facade

    result = facade.ingest(content=b"hello bytes", filename="note.md", kind="note")

    assert seen["existed"] is True
    assert seen["content"] == b"hello bytes"
    assert seen["kind"] == "note"
    assert calls["sync"] == 1  # auto-sync ran
    assert result.status == "ingested"
    assert not Path(seen["path"]).exists()  # temp file cleaned up


def test_ingest_requires_path_or_content():
    from compendium.api import facade

    with pytest.raises(ValueError):
        facade.ingest(kind="note")


# --- integration: read verbs + auto-sync ingest ----------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def seeded(monkeypatch, tmp_path):
    """Migrate compendium_test, ingest the sample fixture, populate both indexes."""
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

    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest as _ingest

    _ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


@pytest.mark.integration
def test_facade_query_pagelist_pageget_status(seeded):
    from compendium.api import facade

    result = facade.query("psychological safety team learning")
    assert result.pages, "expected the source page for a covered query"

    status = facade.index_status()
    assert status.opensearch is not None and status.qdrant is not None

    pages = facade.page_list()
    assert pages and any(p["kind"] == "source" for p in pages)

    first = pages[0]
    got = facade.page_get(first["kind"], first["slug"])
    assert got is not None and got["markdown"]
    assert got["slug"] == first["slug"]

    assert facade.page_get("concept", "does-not-exist-xyz") is None


@pytest.mark.integration
def test_facade_ingest_bytes_autosyncs_and_is_queryable(seeded):
    from compendium.api import facade

    before = facade.index_status()
    before_os = sum((before.opensearch or {}).values())

    note = (
        b"# Deliberate Practice\n\n"
        b"Deliberate practice is focused, effortful repetition with immediate "
        b"feedback, undertaken specifically to improve performance.\n"
    )
    result = facade.ingest(content=note, filename="deliberate-practice.md", kind="note")
    assert result.status in ("ingested", "updated", "unchanged")

    after = facade.index_status()
    after_os = sum((after.opensearch or {}).values())
    assert after_os >= before_os  # the surface auto-ran index sync

    # The new source is retrievable without a manual reindex.
    hits = facade.query("deliberate practice feedback performance")
    assert hits.pages


# --- arch-facade-ingest-coercion: the facade owns the input contract --------


def test_facade_ingest_rejects_missing_input():
    import pytest as _pytest

    from compendium.api import facade

    with _pytest.raises(ValueError, match="ingest requires 'path' or 'content_base64'"):
        facade.ingest(kind="note")


def test_facade_ingest_rejects_invalid_base64():
    import pytest as _pytest

    from compendium.api import facade

    with _pytest.raises(ValueError, match="invalid content_base64"):
        facade.ingest(kind="note", content_base64="@@not-base64@@")


def test_facade_ingest_decodes_base64(monkeypatch):
    """The b64 path round-trips into the bytes path; no transport decodes."""
    import base64 as b64

    from compendium.api import facade

    seen = {}

    def fake_ingest(path, *, kind, mine=False):
        seen["bytes"] = open(path, "rb").read()
        seen["kind"] = kind

        class R:  # one IngestResult-shaped object
            status = "ingested"

        return [R()]

    monkeypatch.setattr("compendium.ingest.pipeline.ingest", fake_ingest)
    monkeypatch.setattr("compendium.index.sync.sync_pending", lambda: None)
    facade.ingest(kind="note", filename="x.md", content_base64=b64.b64encode(b"# Hi").decode())
    assert seen == {"bytes": b"# Hi", "kind": "note"}


def test_transports_contain_no_coercion():
    from pathlib import Path

    for transport in ("compendium/api/http.py", "compendium/api/mcp.py"):
        text = (Path(__file__).resolve().parents[1] / transport).read_text()
        assert "b64decode" not in text, transport
        assert "import base64" not in text, transport
