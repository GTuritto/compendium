"""Unit tests for the v0.2 Phase 5 rule-based query normalizer.

Pure tests: no DB, no live retrieval. AliasIndex.from_db is exercised
under the existing integration tier (the dev DB carries concept aliases);
here we hand-build AliasIndex instances and exercise normalize_query.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from compendium.retrieve.normalize import (
    STOP_WORDS,
    AliasIndex,
    get_alias_index,
    normalize_query,
    refresh_alias_index,
)


# --- AliasIndex ----------------------------------------------------------


def test_alias_index_empty_returns_input_unchanged() -> None:
    idx = AliasIndex.empty()
    assert idx.expand("anything goes here") == "anything goes here"


def test_alias_index_whole_query_match() -> None:
    idx = AliasIndex(_mapping={"psych safety": "psychological safety"})
    assert idx.expand("psych safety") == "psychological safety"


def test_alias_index_word_bounded_substring_match() -> None:
    idx = AliasIndex(_mapping={"psych safety": "psychological safety"})
    assert idx.expand("explore psych safety in teams") == "explore psychological safety in teams"


def test_alias_index_does_not_match_partial_words() -> None:
    """`safe` should not match the alias `psych safety`."""
    idx = AliasIndex(_mapping={"psych safety": "psychological safety"})
    assert idx.expand("psych safetynet test") == "psych safetynet test"


def test_alias_index_longest_alias_first() -> None:
    """When two aliases overlap, the longest one wins."""
    idx = AliasIndex(
        _mapping={
            "safety": "operational safety",
            "psych safety": "psychological safety",
        }
    )
    # "psych safety" should win over "safety" inside "psych safety".
    assert idx.expand("psych safety matters") == "psychological safety matters"


def test_alias_index_preserves_canonical_case() -> None:
    """The mapping value preserves the title's original case."""
    idx = AliasIndex(_mapping={"machine learning": "Machine Learning"})
    assert idx.expand("machine learning") == "Machine Learning"


def test_alias_index_no_aliases_returns_text_unchanged() -> None:
    idx = AliasIndex.empty()
    assert idx.expand("") == ""
    assert idx.expand("any text") == "any text"


def test_alias_index_from_db_reads_concept_aliases() -> None:
    """``from_db`` queries wiki_pages.aliases for concept kind only."""

    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def execute(self, sql):
            return None

        def fetchall(self):
            return self._rows

    class _FakeConn:
        def __init__(self, rows):
            self._rows = rows

        def cursor(self):
            return _FakeCursor(self._rows)

    rows = [
        {"title": "psychological safety", "aliases": ["psych safety", "Psych Safety"]},
        {"title": "Machine Learning", "aliases": ["ML"]},
        {"title": "no aliases", "aliases": None},
    ]
    idx = AliasIndex.from_db(_FakeConn(rows))
    # Both case variants normalize to the same lowercase key.
    assert idx.expand("psych safety") == "psychological safety"
    # `ml` (lowercase) matches; `ML` (uppercase) does not match the alias
    # because the combined regex's input must be already-lowercased.
    assert idx.expand("ml") == "Machine Learning"
    # Skipped at index-build time: aliases=None.
    assert idx.expand("no aliases") == "no aliases"


# --- normalize_query ------------------------------------------------------


def test_normalize_query_lowercases() -> None:
    out = normalize_query("Psychological Safety", AliasIndex.empty())
    assert out == "psychological safety"


def test_normalize_query_strips_stop_words() -> None:
    out = normalize_query("The Psychological Safety concept", AliasIndex.empty())
    # "the" dropped; everything else lowercased.
    assert out == "psychological safety concept"


def test_normalize_query_alias_expansion_runs_after_stop_words() -> None:
    """Per resolved decision #4: lowercase → stop-words → alias expansion."""
    idx = AliasIndex(_mapping={"psych safety": "psychological safety"})
    out = normalize_query("The Psych Safety concept", idx)
    # "The" dropped → "psych safety concept" → "psych safety" matches as
    # a word-bounded substring → "psychological safety concept".
    assert out == "psychological safety concept"


def test_normalize_query_no_match_returns_cleaned_text() -> None:
    idx = AliasIndex(_mapping={"psych safety": "psychological safety"})
    out = normalize_query("An unrelated phrase about cats", idx)
    # Lowercased + "an" stripped; no alias hits.
    assert out == "unrelated phrase about cats"


def test_normalize_query_empty_input() -> None:
    assert normalize_query("", AliasIndex.empty()) == ""
    assert normalize_query("the and of", AliasIndex.empty()) == ""  # all stop-words


def test_normalize_query_uses_module_cache_when_no_index_given(monkeypatch) -> None:
    """A bare ``normalize_query(text)`` call resolves the AliasIndex via
    ``get_alias_index()``.
    """
    refresh_alias_index()  # clear the cache
    called = {"count": 0}

    def _fake_get():
        called["count"] += 1
        return AliasIndex(_mapping={"psych safety": "psychological safety"})

    monkeypatch.setattr("compendium.retrieve.normalize.get_alias_index", _fake_get)
    out = normalize_query("the psych safety story")
    assert out == "psychological safety story"
    assert called["count"] == 1


def test_stop_words_includes_common_function_words() -> None:
    for word in ("the", "a", "an", "and", "or", "of", "for", "in", "on", "at", "to", "from", "is", "are"):
        assert word in STOP_WORDS, f"expected {word!r} in STOP_WORDS"


def test_normalize_query_preserves_case_in_canonical() -> None:
    idx = AliasIndex(_mapping={"ml": "Machine Learning"})
    out = normalize_query("the ML basics", idx)
    # Lowercase first → "ml basics" → "Machine Learning basics".
    assert out == "Machine Learning basics"


# --- get_alias_index module cache ---------------------------------------


def test_get_alias_index_caches_within_a_process(monkeypatch) -> None:
    """First call triggers a DB read; subsequent calls reuse the cache."""
    refresh_alias_index()
    calls = {"count": 0}

    class _FakeCursor:
        def __enter__(self):
            calls["count"] += 1
            return self

        def __exit__(self, *a):
            return None

        def execute(self, sql):
            return None

        def fetchall(self):
            return []

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    @patch("compendium.db.connection.connection")
    def _exercise(mock_connection):
        mock_connection.return_value.__enter__.return_value = _FakeConn()
        mock_connection.return_value.__exit__.return_value = None
        get_alias_index()
        get_alias_index()
        get_alias_index()

    _exercise()
    # The DB cursor was opened exactly once across three get_alias_index calls.
    assert calls["count"] == 1


def test_refresh_alias_index_clears_cache(monkeypatch) -> None:
    refresh_alias_index()
    builds = {"count": 0}

    class _FakeCursor:
        def __enter__(self):
            builds["count"] += 1
            return self

        def __exit__(self, *a):
            return None

        def execute(self, sql):
            return None

        def fetchall(self):
            return []

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    @patch("compendium.db.connection.connection")
    def _exercise(mock_connection):
        mock_connection.return_value.__enter__.return_value = _FakeConn()
        mock_connection.return_value.__exit__.return_value = None
        get_alias_index()
        refresh_alias_index()
        get_alias_index()

    _exercise()
    assert builds["count"] == 2
