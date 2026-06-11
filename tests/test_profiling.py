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


# --- memory half -----------------------------------------------------------


@pytest.fixture
def mem_clean(monkeypatch, tmp_path):
    """An isolated artifacts dir and a disarmed baseline before and after."""
    import tracemalloc

    monkeypatch.setenv("COMPENDIUM_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(profiling, "_mem_baseline", None)
    yield tmp_path
    if tracemalloc.is_tracing():
        tracemalloc.stop()


def test_mem_report_without_arm_is_a_message(mem_clean):
    assert "not armed" in profiling.mem_report()
    assert not list(mem_clean.glob("mem-*.txt"))


def test_mem_arm_then_report_shows_growth_and_writes_artifact(mem_clean):
    profiling.mem_arm()
    hoard = ["x" * 1024 for _ in range(2000)]  # ~2 MiB of tracked growth
    report = profiling.mem_report()
    assert "allocation growth sites since baseline" in report
    assert "traced:" in report and "rss:" in report
    assert __file__.rsplit("/", 1)[-1] in report  # this file is a growth site
    artifacts = list(mem_clean.glob("mem-*.txt"))
    assert len(artifacts) == 1
    assert artifacts[0].read_text().startswith("memory report")
    del hoard


def test_mem_rearm_replaces_baseline(mem_clean):
    profiling.mem_arm()
    first_baseline = profiling._mem_baseline
    profiling.mem_arm()
    assert profiling._mem_baseline is not first_baseline


def test_memory_signal_handlers_never_break_the_process(mem_clean, monkeypatch):
    import os
    import signal

    old_usr1 = signal.getsignal(signal.SIGUSR1)
    old_usr2 = signal.getsignal(signal.SIGUSR2)
    try:
        assert profiling.install_memory_signal_handlers() is True

        def boom(top=15):
            raise RuntimeError("report exploded")

        monkeypatch.setattr(profiling, "mem_arm", lambda: (_ for _ in ()).throw(RuntimeError("arm exploded")))
        monkeypatch.setattr(profiling, "mem_report", boom)
        os.kill(os.getpid(), signal.SIGUSR1)  # arm fails inside the handler
        os.kill(os.getpid(), signal.SIGUSR2)  # report fails inside the handler
        # Reaching here means neither handler let the exception escape.
    finally:
        signal.signal(signal.SIGUSR1, old_usr1)
        signal.signal(signal.SIGUSR2, old_usr2)


def test_memory_signals_drive_arm_and_report(mem_clean):
    import os
    import signal

    old_usr1 = signal.getsignal(signal.SIGUSR1)
    old_usr2 = signal.getsignal(signal.SIGUSR2)
    try:
        profiling.install_memory_signal_handlers()
        os.kill(os.getpid(), signal.SIGUSR1)
        assert profiling._mem_baseline is not None
        os.kill(os.getpid(), signal.SIGUSR2)
        assert list(mem_clean.glob("mem-*.txt"))
    finally:
        signal.signal(signal.SIGUSR1, old_usr1)
        signal.signal(signal.SIGUSR2, old_usr2)
