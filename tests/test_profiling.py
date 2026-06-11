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


def test_profile_dir_default_and_override(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path / "artifacts"))
    d = profiling.profile_dir()
    assert d == tmp_path / "artifacts"
    assert d.is_dir()
    monkeypatch.delenv("COMPENDIUM_PROFILE_DIR")
    assert profiling.profile_dir().name == "profiles"


def test_cpu_profile_writes_loadable_artifact(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path))
    with profiling.cpu_profile("query"):
        sum(range(1000))
    artifacts = list(tmp_path.glob("query-*.prof"))
    assert len(artifacts) == 1
    stats = pstats.Stats(str(artifacts[0]))
    assert stats.total_calls > 0
    err = capsys.readouterr().err
    assert "cpu profile written" in err
    assert "cumulative" in err  # the inline top-25 summary


def test_cpu_profile_slugs_multiword_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path))
    with profiling.cpu_profile("graph rebuild"):
        pass
    assert list(tmp_path.glob("graph-rebuild-*.prof"))


def test_cpu_profile_dump_failure_never_breaks_operation(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path))

    def boom(self, command):
        raise OSError("disk full")

    monkeypatch.setattr(profiling, "_write_cpu_profile", boom)
    result = None
    with profiling.cpu_profile("query"):
        result = 42
    assert result == 42  # the operation's outcome is untouched
    assert not list(tmp_path.glob("*.prof"))


def test_cpu_profile_enable_failure_never_breaks_operation(monkeypatch, tmp_path):
    import cProfile

    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path))

    def boom(self):
        raise RuntimeError("another profiler is active")

    monkeypatch.setattr(cProfile.Profile, "enable", boom)
    result = None
    with profiling.cpu_profile("query"):
        result = 42
    assert result == 42


def test_cpu_profile_block_exception_passes_through(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="boom"):
        with profiling.cpu_profile("query"):
            raise ValueError("boom")
    # The artifact is still written for the failed run.
    assert list(tmp_path.glob("query-*.prof"))
