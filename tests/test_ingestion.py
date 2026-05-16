"""Phase 2 ingestion tests: unit checks plus an integration walk.

The integration tests run the pipeline against a dedicated ``compendium_test``
database and skip when PostgreSQL is unreachable.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.ingest.adapters.base import Section
from compendium.ingest.chunking import chunk_sections
from compendium.ingest.hashing import estimate_tokens, hash_bytes, hash_text
from compendium.ingest.inspection import FAILED, PASSED, PASSED_WITH_WARNINGS, inspect
from compendium.ingest.adapters.base import ParsedSource
from compendium.ingest.pipeline import ingest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit tests ------------------------------------------------------------


def test_hash_bytes_is_stable_and_sensitive():
    assert hash_bytes(b"abc") == hash_bytes(b"abc")
    assert hash_bytes(b"abc") != hash_bytes(b"abd")


def test_hash_text_ignores_cosmetic_whitespace():
    assert hash_text("a  b\n c") == hash_text("a b c")
    assert hash_text("a b") != hash_text("a c")


def test_estimate_tokens_grows_with_length():
    assert estimate_tokens("x" * 400) > estimate_tokens("x" * 40)


def test_chunking_respects_section_boundaries():
    sections = [Section("Intro", "short intro"), Section("Body", "the body")]
    chunks = chunk_sections(sections, target_tokens=512, overlap_tokens=64)
    assert [c.parent_section for c in chunks] == ["Intro", "Body"]
    assert [c.position for c in chunks] == [0, 1]


def test_chunking_windows_large_sections():
    big = " ".join(f"distinct sentence {i}." for i in range(1500))
    chunks = chunk_sections([Section("", big)], target_tokens=512, overlap_tokens=64)
    assert len(chunks) > 1
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_chunking_dedupes_identical_bodies():
    sections = [Section("A", "same body"), Section("B", "same body")]
    assert len(chunk_sections(sections, target_tokens=512, overlap_tokens=64)) == 1


def test_markdown_adapter_uses_first_h1_as_title():
    from compendium.ingest.adapters.dispatch import parse_source

    parsed = parse_source(str(_FIXTURES / "sample.md"))
    assert parsed.metadata.get("title") == "Sample Markdown Source"


def test_inspection_classifies():
    healthy = ParsedSource("word " * 2000, [], {})
    thin = ParsedSource("only a few words", [], {})
    empty = ParsedSource("   ", [], {})
    args = {"max_source_bytes": 10**8, "min_text_tokens": 1000}
    assert inspect(healthy, b"x" * 9000, **args).status == PASSED
    assert inspect(thin, b"x" * 20, **args).status == PASSED_WITH_WARNINGS
    assert inspect(empty, b"", **args).status == FAILED


# --- integration tests -----------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def ingest_db(monkeypatch) -> str:
    """A migrated, empty compendium_test database; POSTGRES_URL points at it."""
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


def test_ingest_three_formats(ingest_db: str) -> None:
    for name, kind in [
        ("sample.md", "note"),
        ("sample.html", "web"),
        ("sample.pdf", "paper"),
    ]:
        results = ingest(str(_FIXTURES / name), kind=kind)
        assert len(results) == 1
        result = results[0]
        assert result.status == "ingested"
        assert result.chunk_count > 0

    with psycopg.connect(ingest_db) as conn:
        sources = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
        chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        # no two chunks of a source share a body hash
        dupes = conn.execute(
            "SELECT count(*) FROM ("
            "  SELECT source_id, body_hash FROM chunks"
            "  GROUP BY source_id, body_hash HAVING count(*) > 1"
            ") d"
        ).fetchone()[0]
    assert sources == 3
    assert chunks > 0
    assert dupes == 0


def test_reingest_is_idempotent(ingest_db: str) -> None:
    path = str(_FIXTURES / "sample.md")
    first = ingest(path, kind="note")[0]
    assert first.status == "ingested"
    second = ingest(path, kind="note")[0]
    assert second.status == "unchanged"

    with psycopg.connect(ingest_db) as conn:
        sources = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
        chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    assert sources == 1
    assert chunks == first.chunk_count


def test_failed_source_appears_in_view(ingest_db: str) -> None:
    result = ingest(str(_FIXTURES / "broken.pdf"), kind="paper")[0]
    assert result.status == "failed"

    with psycopg.connect(ingest_db) as conn:
        failed = conn.execute("SELECT title FROM v_failed_sources").fetchall()
        notes = conn.execute(
            "SELECT inspection_notes FROM sources WHERE inspection_status = 'failed'"
        ).fetchone()[0]
    assert len(failed) == 1
    assert notes  # a non-empty reason was recorded


def test_authored_provenance(ingest_db: str) -> None:
    ingest(str(_FIXTURES / "sample.md"), kind="note", mine=True)
    with psycopg.connect(ingest_db) as conn:
        metadata = conn.execute("SELECT metadata FROM sources").fetchone()[0]
    assert metadata.get("authored_by_me") is True
