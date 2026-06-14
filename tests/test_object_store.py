"""Agent object store (ADR-017, v0.5).

Integration (migrated ``compendium_test`` DB; skips if PostgreSQL is down). The
store + facade serialization are tested here; the promote path (which crosses
all stores) is verified by the manual smoke playbook (v0.5-obj.3/4).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def test_db(monkeypatch):
    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")
    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")
    monkeypatch.setenv("POSTGRES_URL", test_url)
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def test_put_get_verbatim(test_db):
    """TC-OS-U1 / AC-OS-1 (O1): bytes round-trip byte-for-byte."""
    from compendium import objects

    blob = b"\x00\x01\x02 binary \xff and text"
    objects.put("k1", blob, content_type="application/octet-stream")
    row = objects.get("k1")
    assert row is not None
    assert row["body"] == blob  # verbatim
    assert row["content_type"] == "application/octet-stream"


def test_upsert_is_last_write_wins(test_db):
    """TC-OS-U2: a second put on the same (collection,key) overwrites."""
    from compendium import objects

    objects.put("k", b"v1")
    objects.put("k", b"v2", metadata={"n": 2})
    row = objects.get("k")
    assert row["body"] == b"v2"
    assert row["metadata"] == {"n": 2}
    assert len(objects.list_objects(collection="default")) == 1  # not duplicated


def test_list_and_delete(test_db):
    """TC-OS-U3."""
    from compendium import objects

    objects.put("a", b"x")
    objects.put("b", b"y")
    keys = {r["key"] for r in objects.list_objects(collection="default")}
    assert {"a", "b"} <= keys
    assert objects.delete("a") is True
    assert objects.get("a") is None
    assert objects.delete("a") is False  # idempotent


def test_facade_serialization(test_db):
    """TC-OS-U4 / AC-OS-3: facade payloads are JSON-native and verbatim."""
    from compendium.api import facade

    facade.object_put("doc", content_text="hello world", content_type="text/markdown")
    got = facade.object_get("doc")
    # JSON-serializable (the transports json.dumps this)
    json.dumps(got)
    assert got["body_text"] == "hello world"
    assert base64.b64decode(got["body_base64"]) == b"hello world"  # verbatim
    listed = facade.object_list(collection="default")
    json.dumps(listed)
    assert any(r["key"] == "doc" for r in listed)
    assert facade.object_get("missing") is None
