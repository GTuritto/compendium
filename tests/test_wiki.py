"""Phase 3 wiki-generation tests: unit checks plus an integration walk.

Integration tests run against a dedicated ``compendium_test`` database and a
temporary vault, and skip when PostgreSQL is unreachable.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.wiki.lint import errors_only, lint_page
from compendium.wiki.page import Page, content_hash, parse_markdown
from compendium.wiki.slug import slugify
from compendium.wiki.synth import StubSynthesizer, synthesize_concept

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"

_ISO = "2026-01-01T00:00:00+00:00"
_UUID = "11111111-1111-1111-1111-111111111111"


# --- unit tests ------------------------------------------------------------


def test_slugify_rules():
    assert slugify("Café Society") == "cafe-society"
    assert slugify("Hello   World") == "hello-world"
    assert slugify("Safety", {"safety"}) == "safety-2"
    assert len(slugify("word " * 100)) <= 80


def test_content_hash_ignores_frontmatter_only_change():
    body = "# Title\n\nThe body text."
    draft = Page(kind="concept", title="T", slug="t", body=body, status="draft")
    canonical = Page(
        kind="concept", title="T", slug="t", body=body, status="canonical"
    )
    assert content_hash(draft.body) == content_hash(canonical.body)


def test_page_round_trips_through_markdown():
    page = Page(
        kind="source",
        title="A Source",
        slug="a-source",
        body="# A Source\n\nBody.",
        id=_UUID,
        created_at=_ISO,
        updated_at=_ISO,
        content_hash="h",
        corpus_revision="rev-x",
        source_id="22222222-2222-2222-2222-222222222222",
        source_kind="book",
        source_metadata={"year": 2020},
        inspection_status="passed",
    )
    back = parse_markdown(page.to_markdown())
    assert back.kind == "source"
    assert back.source_id == page.source_id
    assert back.source_metadata == {"year": 2020}
    assert back.body == page.body


def test_lint_rejects_an_invalid_page():
    bad = Page(kind="concept", title="X", slug="Bad Slug", body="", id="not-a-uuid")
    assert errors_only(lint_page(bad))


def test_lint_accepts_a_valid_page():
    body = "# X\n\nReal body."
    good = Page(
        kind="topic",
        title="X",
        slug="x",
        body=body,
        id=_UUID,
        status="draft",
        generator="synth",
        corpus_revision="rev-x",
        created_at=_ISO,
        updated_at=_ISO,
        content_hash=content_hash(body),
    )
    assert not errors_only(lint_page(good))


# --- integration tests -----------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def wiki_env(monkeypatch, tmp_path) -> tuple[str, str]:
    """A migrated compendium_test database and a temporary vault."""
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
    yield test_url, str(vault)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def test_source_page_generated_on_ingest(wiki_env: tuple[str, str]) -> None:
    db_url, vault = wiki_env
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.md"), kind="note")

    source_pages = list(Path(vault, "sources").glob("*.md"))
    assert len(source_pages) == 1

    page = parse_markdown(source_pages[0].read_text(encoding="utf-8"))
    assert page.kind == "source"
    assert not errors_only(lint_page(page))

    with psycopg.connect(db_url) as conn:
        revisions = conn.execute(
            "SELECT count(*) FROM wiki_page_revisions"
        ).fetchone()[0]
        current = conn.execute(
            "SELECT count(*) FROM wiki_pages WHERE current_revision_id IS NOT NULL"
        ).fetchone()[0]
    assert revisions == 1
    assert current == 1


def test_concept_synthesis_grounds_across_sources(
    wiki_env: tuple[str, str],
) -> None:
    db_url, vault = wiki_env
    from compendium.db.connection import connection
    from compendium.ingest.pipeline import ingest

    ingest(str(_FIXTURES / "sample.pdf"), kind="paper")
    ingest(str(_FIXTURES / "sample.md"), kind="note")

    with connection() as conn:
        page = synthesize_concept(
            conn,
            "psychological safety",
            vault_path=vault,
            synthesizer=StubSynthesizer(),
        )

    assert page.kind == "concept"
    assert not errors_only(lint_page(page))

    grounding = page.body.split("## Grounding", 1)[1]
    assert grounding.count("- chunk ") >= 2
    assert "Sample PDF Source" in grounding
    assert "Sample Markdown Source" in grounding

    assert Path(vault, "concepts", "psychological-safety.md").is_file()
