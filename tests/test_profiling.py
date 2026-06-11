"""Unit tests for the local profiler (compendium/profiling.py)."""

from __future__ import annotations

import pstats

import pytest

from compendium import profiling


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        (" 1 ", True),
        ("", False),
        ("0", False),
        ("false", False),
        ("False", False),
        ("no", False),
        ("off", False),
        ("OFF", False),
    ],
)
def test_enabled_truthiness(monkeypatch, value, expected):
    monkeypatch.setenv("COMPENDIUM_PROFILE", value)
    assert profiling.enabled() is expected


def test_enabled_defaults_off(monkeypatch):
    monkeypatch.delenv("COMPENDIUM_PROFILE", raising=False)
    assert profiling.enabled() is False


def test_timed_fills_sink(monkeypatch):
    monkeypatch.delenv("COMPENDIUM_PROFILE", raising=False)
    sink: dict[str, float] = {}
    with profiling.timed("stage", sink=sink):
        pass
    assert isinstance(sink["stage"], float)
    assert sink["stage"] >= 0.0


def test_timed_fills_sink_on_exception(monkeypatch):
    monkeypatch.delenv("COMPENDIUM_PROFILE", raising=False)
    sink: dict[str, float] = {}
    with pytest.raises(ValueError):
        with profiling.timed("stage", sink=sink):
            raise ValueError("boom")
    assert "stage" in sink


def test_timed_without_sink_is_silent_noop(monkeypatch):
    monkeypatch.delenv("COMPENDIUM_PROFILE", raising=False)
    with profiling.timed("stage"):
        pass  # nothing to assert beyond "does not raise"


def test_cpu_profile_writes_loadable_stats(tmp_path):
    out = tmp_path / "run.prof"
    with profiling.cpu_profile(str(out)):
        sum(range(1000))
    assert out.is_file()
    stats = pstats.Stats(str(out))
    assert stats.total_calls > 0
