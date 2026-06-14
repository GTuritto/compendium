"""Curation autonomy knob (ADR-022, v0.5).

Integration: migrated ``compendium_test`` DB + a tmp vault + the stub
synthesizer; skips if PostgreSQL is unreachable.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.db import repository

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def env(monkeypatch, tmp_path):
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

    vault = tmp_path / "vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True)
    monkeypatch.setenv("POSTGRES_URL", test_url)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("COMPENDIUM_SYNTH_STUB", "1")
    monkeypatch.setenv("COMPENDIUM_EMBED_STUB", "1")

    from compendium.db.connection import connection

    with connection() as conn:
        yield conn, str(vault)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _seed_corpus(conn) -> None:
    """A source + a chunk that mentions the target, so synth has context."""
    sid = repository.insert_source(
        conn, kind="note", title="Widgets", content_hash="wc"
    )
    repository.insert_chunks(conn, sid, [
        SimpleNamespace(
            position=0, parent_section=None,
            body="Widget Theory explains how widgets compose.",
            body_hash="wh", token_count=6,
        )
    ])
    conn.commit()


def _gap_signal(conn) -> str:
    sid = repository.insert_curation_signal(
        conn, kind="gap", priority=1,
        payload={"query_text": "what is widget theory", "missing_concepts": ["Widget Theory"]},
    )
    conn.commit()
    return str(sid)


def test_default_mode_is_semi_auto():
    """TC-CK-U1."""
    from compendium import config_sections

    assert config_sections.curation()["mode"] == "semi-auto"


def test_manual_is_a_noop(env):
    """TC-CK-U2 / AC-CK-2 (C2)."""
    from compendium.curate.autocurate import autocurate

    conn, vault = env
    sid = _gap_signal(conn)
    rep = autocurate(conn, [sid], mode="manual", vault_path=vault)
    assert (rep.drafted, rep.promoted) == (0, 0)
    assert repository.get_wiki_page_by_slug(conn, "concept", "widget-theory") is None


def test_semi_auto_drafts_but_does_not_promote(env):
    """TC-CK-U3 / AC-CK-1 (C1)."""
    from compendium.curate.autocurate import autocurate

    conn, vault = env
    _seed_corpus(conn)
    sid = _gap_signal(conn)
    rep = autocurate(conn, [sid], mode="semi-auto", vault_path=vault)
    assert rep.drafted == 1 and rep.promoted == 0
    page = repository.get_wiki_page_by_slug(conn, "concept", "widget-theory")
    assert page is not None and page["status"] == "draft"  # not canonical (C1)


def test_auto_promotes(env):
    """TC-CK-U4 / AC-CK-3."""
    from compendium.curate.autocurate import autocurate

    conn, vault = env
    _seed_corpus(conn)
    sid = _gap_signal(conn)
    rep = autocurate(conn, [sid], mode="auto", vault_path=vault, confidence=0.8)
    assert rep.drafted == 1 and rep.promoted == 1
    page = repository.get_wiki_page_by_slug(conn, "concept", "widget-theory")
    assert page is not None and page["status"] == "canonical"


def test_auto_shadow_drafts_without_promoting(env):
    """TC-CK-U5."""
    from compendium.curate.autocurate import autocurate

    conn, vault = env
    sid = _gap_signal(conn)
    rep = autocurate(conn, [sid], mode="auto", vault_path=vault, shadow=True)
    assert rep.promoted == 0
    # shadow records intent but writes nothing
    assert repository.get_wiki_page_by_slug(conn, "concept", "widget-theory") is None


def test_never_overwrites_a_curator_page(env):
    """TC-CK-U6 / AC-CK-4 (C4)."""
    from compendium.curate.autocurate import autocurate

    conn, vault = env
    # a human-authored canonical page already owns the slug
    repository.insert_wiki_page(
        conn, kind="concept", slug="widget-theory", title="Widget Theory",
        file_path="concepts/widget-theory.md", content_hash="h",
        status="canonical",
    )
    conn.commit()
    sid = _gap_signal(conn)
    rep = autocurate(conn, [sid], mode="auto", vault_path=vault)
    assert rep.drafted == 0 and rep.skipped == 1  # not overwritten
    page = repository.get_wiki_page_by_slug(conn, "concept", "widget-theory")
    assert page["status"] == "canonical"  # untouched
