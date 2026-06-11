"""Tests for the ``compendium/service_unit/`` seam.

Two guards:

1. **Parity** — for each of the four services, the seam renders byte-for-byte
   what that service's module generates today (curate/backup/inbox/serve, both
   the plist and the systemd unit(s)). This is the behaviour-preserving contract.
2. **Lifecycle** — install / uninstall / probe drive the right ``launchctl`` /
   ``systemctl`` argv through an injected fake :class:`Runner`, raise
   ``ServiceUnitError`` with the preserved ``step`` on a non-zero exit, and are
   idempotent — all without a real scheduler.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compendium.service_unit import (
    AlwaysOn,
    Calendar,
    Interval,
    ServiceUnitError,
    UnitDescriptor,
    WatchPaths,
    launchd,
    platform,
    systemd,
)
from compendium.service_unit.runner import RunResult


# --- fixtures: the descriptor each service builds --------------------------


def _curate_descriptor() -> UnitDescriptor:
    from compendium.schedule import install as sched

    return UnitDescriptor(
        label=sched.LABEL,
        linux_basename=sched.LINUX_UNIT_BASENAME,
        program_args=sched._build_program_args(),
        working_dir=sched._repo_root(),
        trigger=Interval(3600),
        service_description="Compendium curation slow loop",
        log_basename="curate",
        trigger_description="Compendium curation slow-loop timer (every 3600s)",
    )


def _backup_descriptor() -> UnitDescriptor:
    from compendium.backup import schedule as bk

    return UnitDescriptor(
        label=bk._LABEL,
        linux_basename=bk._LINUX_UNIT_BASENAME,
        program_args=bk._build_program_args(),
        working_dir=bk._repo_root(),
        trigger=Calendar(2, 0),
        service_description="Compendium backup (PostgreSQL + vault)",
        log_basename="backup",
        trigger_description="Daily Compendium backup at 02:00",
    )


def _inbox_descriptor(inbox: Path) -> UnitDescriptor:
    from compendium.inbox import install as ib

    return UnitDescriptor(
        label=ib.LABEL,
        linux_basename=ib.LINUX_UNIT_BASENAME,
        program_args=ib._build_program_args(inbox),
        working_dir=ib._repo_root(),
        trigger=WatchPaths(tuple(f"{inbox}/{k}" for k in ib.INBOX_KINDS)),
        service_description="Compendium inbox processor",
        log_basename="inbox",
        trigger_description="Compendium inbox watcher (PathChanged on every kind subdir)",
    )


def _serve_descriptor(host: str, port: int) -> UnitDescriptor:
    from compendium.api import service as sv

    return UnitDescriptor(
        label=sv.LABEL,
        linux_basename=sv.LINUX_UNIT_BASENAME,
        program_args=sv._program_args(host, port),
        working_dir=sv._repo_root(),
        trigger=AlwaysOn(),
        service_description=f"Compendium access surface (HTTP, {host}:{port})",
        log_basename="serve",
        detail_suffix=f" on {host}:{port}",
    )


# --- parity: seam render == current module output --------------------------


def test_curate_render_matches_current_module() -> None:
    from compendium.schedule import install as sched

    d = _curate_descriptor()
    assert launchd.render(d) == sched._macos_plist_xml(3600)
    assert systemd.render_service(d) == sched._linux_service_unit()
    assert systemd.render_trigger(d) == sched._linux_timer_unit(3600)


def test_backup_render_matches_current_module() -> None:
    from compendium.backup import schedule as bk

    d = _backup_descriptor()
    assert launchd.render(d) == bk._macos_plist_xml(2, 0)
    assert systemd.render_service(d) == bk._linux_service_unit()
    assert systemd.render_trigger(d) == bk._linux_timer_unit(2, 0)


def test_inbox_render_matches_current_module() -> None:
    from compendium.inbox import install as ib

    inbox = Path("/INBOX")
    d = _inbox_descriptor(inbox)
    assert launchd.render(d) == ib._macos_plist_xml(inbox)
    assert systemd.render_service(d) == ib._linux_service_unit(inbox)
    assert systemd.render_trigger(d) == ib._linux_path_unit(inbox)


def test_serve_render_matches_current_module() -> None:
    from compendium.api import service as sv

    d = _serve_descriptor("127.0.0.1", 8787)
    assert launchd.render(d) == sv._macos_plist_xml("127.0.0.1", 8787)
    assert systemd.render_service(d) == sv._linux_service_unit("127.0.0.1", 8787)


# --- the trigger taxonomy renders the right keys ---------------------------


def test_interval_renders_start_interval_and_on_unit_active_sec() -> None:
    d = _curate_descriptor()
    assert "<key>StartInterval</key>" in launchd.render(d)
    assert "<integer>3600</integer>" in launchd.render(d)
    timer = systemd.render_trigger(d)
    assert "OnUnitActiveSec=3600" in timer and "OnBootSec=3600" in timer


def test_calendar_renders_wall_clock_keys() -> None:
    d = _backup_descriptor()
    assert "<key>StartCalendarInterval</key>" in launchd.render(d)
    assert "OnCalendar=*-*-* 02:00:00" in systemd.render_trigger(d)


def test_watchpaths_renders_one_entry_per_path() -> None:
    d = _inbox_descriptor(Path("/INBOX"))
    plist = launchd.render(d)
    trig = systemd.render_trigger(d)
    for kind in ("book", "article", "paper", "note", "web"):
        assert f"<string>/INBOX/{kind}</string>" in plist
        assert f"PathChanged=/INBOX/{kind}" in trig
    assert "WantedBy=paths.target" in trig


def test_alwayson_renders_keepalive_and_restart() -> None:
    d = _serve_descriptor("127.0.0.1", 8787)
    plist = launchd.render(d)
    assert "<key>RunAtLoad</key>" in plist and "<true/>" in plist
    assert "<key>KeepAlive</key>" in plist
    service = systemd.render_service(d)
    assert "Restart=always" in service and "WantedBy=default.target" in service
    # AlwaysOn has no companion timer/path unit.
    assert systemd.render_trigger(d) is None


# --- lifecycle through a fake runner ---------------------------------------


class FakeRunner:
    def __init__(self, *, fail_on: str | None = None, stdout: str = "") -> None:
        self.calls: list[list[str]] = []
        self._fail_on = fail_on
        self._stdout = stdout

    def run(self, args: list[str]) -> RunResult:
        self.calls.append(args)
        if self._fail_on and self._fail_on in args:
            return RunResult(1, stderr="boom")
        return RunResult(0, stdout=self._stdout)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path


def test_launchd_install_writes_plist_and_bootstraps(home) -> None:
    d = _curate_descriptor()
    runner = FakeRunner()
    result = launchd.install(d, runner=runner)
    plist = launchd.plist_path(d.label)
    assert plist.exists()
    assert result.action == "install" and result.detail == f"loaded {d.label}"
    # bootout (best-effort) then bootstrap.
    assert any("bootout" in c for c in runner.calls)
    assert any("bootstrap" in c for c in runner.calls)


def test_launchd_install_raises_on_bootstrap_failure(home) -> None:
    runner = FakeRunner(fail_on="bootstrap")
    with pytest.raises(ServiceUnitError) as excinfo:
        launchd.install(_curate_descriptor(), runner=runner)
    assert excinfo.value.step == "launchctl_bootstrap"


def test_launchd_uninstall_is_idempotent(home) -> None:
    d = _curate_descriptor()
    runner = FakeRunner()
    launchd.install(d, runner=runner)
    first = launchd.uninstall(d, runner=runner)
    second = launchd.uninstall(d, runner=runner)
    assert first.detail == "removed"
    assert second.detail == "not installed"


def test_systemd_install_writes_units_and_enables(home) -> None:
    d = _curate_descriptor()
    runner = FakeRunner()
    result = systemd.install(d, runner=runner)
    assert systemd.service_path(d).exists()
    assert systemd.trigger_unit_path(d).exists()
    assert result.detail == f"enabled {d.linux_basename}.timer"
    assert any("daemon-reload" in c for c in runner.calls)
    assert any("enable" in c and "--now" in c for c in runner.calls)


def test_systemd_install_raises_on_enable_failure(home) -> None:
    runner = FakeRunner(fail_on="enable")
    with pytest.raises(ServiceUnitError) as excinfo:
        systemd.install(_curate_descriptor(), runner=runner)
    assert excinfo.value.step == "systemctl_enable"


def test_systemd_uninstall_is_idempotent(home) -> None:
    d = _curate_descriptor()
    runner = FakeRunner()
    systemd.install(d, runner=runner)
    first = systemd.uninstall(d, runner=runner)
    second = systemd.uninstall(d, runner=runner)
    assert first.detail.startswith("removed ")
    assert second.detail == "not installed"


def test_systemd_alwayson_installs_service_only(home) -> None:
    d = _serve_descriptor("127.0.0.1", 8787)
    runner = FakeRunner()
    result = systemd.install(d, runner=runner)
    assert systemd.service_path(d).exists()
    assert systemd.trigger_unit_path(d) is None
    assert result.detail == f"enabled {d.linux_basename}.service on 127.0.0.1:8787"


def test_loaded_false_when_absent(home) -> None:
    assert systemd.loaded(_curate_descriptor(), runner=FakeRunner()) is False
    assert launchd.probe(_curate_descriptor(), runner=FakeRunner()).loaded is False


def test_platform_rejects_unsupported(monkeypatch) -> None:
    import compendium.service_unit as su

    monkeypatch.setattr(su.sys, "platform", "freebsd14")
    with pytest.raises(ServiceUnitError) as excinfo:
        su.platform()
    assert excinfo.value.step == "platform"
    assert "freebsd14" in excinfo.value.detail


def test_systemd_probe_activity_runs_status_and_timers_for_triggered_units(tmp_path, monkeypatch):
    from compendium.service_unit import Interval, systemd

    monkeypatch.setattr(systemd, "unit_dir", lambda: tmp_path)
    desc = UnitDescriptor(
        label="com.compendium.curate", linux_basename="compendium-curate",
        program_args=["x"], working_dir=tmp_path, trigger=Interval(3600),
        service_description="d", log_basename="curate",
    )
    (tmp_path / "compendium-curate.timer").write_text("[Timer]\n")
    runner = FakeRunner()
    probe = systemd.probe_activity(desc, runner=runner)
    cmds = [" ".join(c) for c in runner.calls]
    assert any("status compendium-curate.timer" in c for c in cmds)
    assert any("list-timers --all compendium-curate.timer" in c for c in cmds)
    assert probe.unit_path == tmp_path / "compendium-curate.timer"


def test_systemd_probe_activity_skips_timers_for_alwayson(tmp_path, monkeypatch):
    from compendium.service_unit import AlwaysOn, systemd

    monkeypatch.setattr(systemd, "unit_dir", lambda: tmp_path)
    desc = UnitDescriptor(
        label="com.compendium.serve", linux_basename="compendium-serve",
        program_args=["x"], working_dir=tmp_path, trigger=AlwaysOn(),
        service_description="d", log_basename="serve",
    )
    (tmp_path / "compendium-serve.service").write_text("[Service]\n")
    runner = FakeRunner()
    systemd.probe_activity(desc, runner=runner)
    cmds = [" ".join(c) for c in runner.calls]
    assert any("status compendium-serve.service" in c for c in cmds)
    assert not any("list-timers" in c for c in cmds)
