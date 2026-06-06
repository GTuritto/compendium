"""Scheduled curation tests (v0.2 Phase 3).

Unit: cadence parsing, plist + systemd unit content, platform-detect
guard. Integration: install → manual kick → assert one new
`graph_analysis_runs` row → uninstall. The integration test lands in
sub-phase 3d alongside the operational doc and smoke section.
"""

from __future__ import annotations

import pytest

from compendium.schedule import ScheduleError, parse_interval


# --- cadence parsing ------------------------------------------------------


def test_parse_interval_accepts_hours() -> None:
    assert parse_interval("1h") == 3600
    assert parse_interval("2h") == 7200
    assert parse_interval("24h") == 86400


def test_parse_interval_accepts_minutes() -> None:
    assert parse_interval("1m") == 60
    assert parse_interval("30m") == 1800
    assert parse_interval("60m") == 3600


def test_parse_interval_accepts_hours_and_minutes() -> None:
    assert parse_interval("1h30m") == 5400
    assert parse_interval("2h30m") == 9000
    assert parse_interval("0h30m") == 1800


def test_parse_interval_is_case_insensitive() -> None:
    assert parse_interval("1H") == 3600
    assert parse_interval("30M") == 1800


def test_parse_interval_rejects_below_minimum() -> None:
    with pytest.raises(ScheduleError) as excinfo:
        parse_interval("30s")
    assert excinfo.value.step == "parse"


def test_parse_interval_rejects_above_maximum() -> None:
    with pytest.raises(ScheduleError) as excinfo:
        parse_interval("200h")  # 200h = 720000s > 7d (604800s)
    assert excinfo.value.step == "parse"
    assert "7-day" in excinfo.value.detail


def test_parse_interval_rejects_zero() -> None:
    with pytest.raises(ScheduleError):
        parse_interval("0h")
    with pytest.raises(ScheduleError):
        parse_interval("0m")
    with pytest.raises(ScheduleError):
        parse_interval("0h0m")


def test_parse_interval_rejects_malformed() -> None:
    for bad in ("", "abc", "1", "1d", "h", "m", "1.5h", " "):
        with pytest.raises(ScheduleError):
            parse_interval(bad)


# --- macOS plist content --------------------------------------------------


def test_macos_plist_xml_contains_start_interval() -> None:
    from compendium.schedule.install import LABEL, _macos_plist_xml

    xml = _macos_plist_xml(3600)
    assert LABEL in xml
    assert "<key>StartInterval</key>" in xml
    assert "<integer>3600</integer>" in xml
    assert "ProgramArguments" in xml
    # The command should target the curate verb.
    assert "curate" in xml


def test_macos_plist_xml_carries_the_right_interval() -> None:
    from compendium.schedule.install import _macos_plist_xml

    for seconds in (60, 1800, 3600, 86400):
        xml = _macos_plist_xml(seconds)
        assert f"<integer>{seconds}</integer>" in xml


# --- Linux systemd unit content -------------------------------------------


def test_linux_timer_unit_contains_on_unit_active_sec() -> None:
    from compendium.schedule.install import _linux_service_unit, _linux_timer_unit

    timer = _linux_timer_unit(3600)
    assert "OnUnitActiveSec=3600" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer
    service = _linux_service_unit()
    assert "ExecStart=" in service
    assert "compendium" in service
    assert "curate run" in service


def test_linux_timer_unit_carries_the_right_interval() -> None:
    from compendium.schedule.install import _linux_timer_unit

    for seconds in (60, 1800, 3600, 86400):
        timer = _linux_timer_unit(seconds)
        assert f"OnUnitActiveSec={seconds}" in timer


# --- platform guard -------------------------------------------------------


def test_platform_detect_refuses_unsupported(monkeypatch) -> None:
    # Platform detection now lives once, in the shared service_unit seam.
    import compendium.service_unit as su

    monkeypatch.setattr(su.sys, "platform", "freebsd14")
    with pytest.raises(ScheduleError) as excinfo:  # ScheduleError is an alias of ServiceUnitError
        su.platform()
    assert excinfo.value.step == "platform"
    assert "freebsd14" in excinfo.value.detail


# --- status ---------------------------------------------------------------


def test_status_when_unit_absent(monkeypatch, tmp_path) -> None:
    from compendium.schedule import status as status_module

    # Force the macOS plist path to a tmp location that does not exist.
    monkeypatch.setattr(status_module, "_macos_plist_path", lambda: tmp_path / "absent.plist")
    monkeypatch.setattr(status_module.sys, "platform", "darwin")
    s = status_module.read_status()
    assert s.loaded is False
    assert s.state == "absent"
    assert s.last_fired is None
    assert s.next_fire is None


def test_status_parses_macos_launchctl_output(monkeypatch, tmp_path) -> None:
    from compendium.schedule import status as status_module

    plist = tmp_path / "exists.plist"
    plist.write_text("<plist/>")
    monkeypatch.setattr(status_module, "_macos_plist_path", lambda: plist)
    monkeypatch.setattr(status_module.sys, "platform", "darwin")

    fake_stdout = """gui/501/com.compendium.curate = {
\tactive count = 0
\tpath = /tmp/exists.plist
\ttype = LaunchAgent
\tstate = not running

\tlast exit code = (never exited)
\trun interval = 1800 seconds
"""

    class _Result:
        returncode = 0
        stdout = fake_stdout
        stderr = ""

    monkeypatch.setattr(status_module.subprocess, "run", lambda *a, **k: _Result())

    s = status_module.read_status()
    assert s.loaded is True
    assert s.state == "not running"
    assert s.last_fired == "(never exited)"
    assert s.next_fire is None  # macOS does not surface next-fire
    assert s.interval_seconds == 1800


def test_status_when_launchctl_returns_nonzero(monkeypatch, tmp_path) -> None:
    """Plist exists on disk but the unit is not loaded into launchd."""
    from compendium.schedule import status as status_module

    plist = tmp_path / "exists.plist"
    plist.write_text("<plist/>")
    monkeypatch.setattr(status_module, "_macos_plist_path", lambda: plist)
    monkeypatch.setattr(status_module.sys, "platform", "darwin")

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "service not found"

    monkeypatch.setattr(status_module.subprocess, "run", lambda *a, **k: _Result())

    s = status_module.read_status()
    assert s.loaded is False
    assert s.state == "not loaded"


def test_status_dataclass_to_dict_stringifies_path(tmp_path) -> None:
    from compendium.schedule.status import ScheduleStatus

    s = ScheduleStatus(
        loaded=True,
        unit_path=tmp_path / "x.plist",
        state="not running",
        last_fired="(never exited)",
        next_fire=None,
        interval_seconds=3600,
    )
    d = s.to_dict()
    assert isinstance(d["unit_path"], str)
    assert d["interval_seconds"] == 3600


# --- integration round-trip ----------------------------------------------


@pytest.mark.integration
def test_schedule_install_kick_uninstall(tmp_path) -> None:
    """Install → manually kick the unit → observe one new
    `graph_analysis_runs` row → uninstall (idempotent).

    Skips when the OS scheduler is not the curator's user session
    (no DISPLAY / no `gui/<uid>/` domain), when PostgreSQL is
    unreachable, or when running in CI without a writable
    `~/Library/LaunchAgents` or `~/.config/systemd/user/`.
    """
    import os
    import shutil
    import subprocess
    import sys
    import time

    import psycopg
    from psycopg.rows import dict_row

    from compendium.config import load_config
    from compendium.schedule import (
        install_schedule,
        read_status,
        uninstall_schedule,
    )

    if sys.platform == "darwin":
        if shutil.which("launchctl") is None:
            pytest.skip("launchctl not on PATH")
    elif sys.platform.startswith("linux"):
        if shutil.which("systemctl") is None:
            pytest.skip("systemctl not on PATH")
    else:
        pytest.skip(f"unsupported platform for integration test: {sys.platform}")

    try:
        with psycopg.connect(load_config().postgres_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM graph_analysis_runs")
                pre_count = cur.fetchone()["n"]
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    # Always uninstall on test exit, even when the assertions fail.
    install_schedule(3600)
    try:
        status = read_status()
        assert status.loaded is True
        assert status.unit_path.exists()

        # Kick the unit and wait for the curate run to land a row.
        if sys.platform == "darwin":
            uid = os.getuid()
            subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{uid}/com.compendium.curate"],
                capture_output=True, text=True, check=False,
            )
        else:
            subprocess.run(
                ["systemctl", "--user", "start", "compendium-curate.service"],
                capture_output=True, text=True, check=False,
            )

        deadline = time.time() + 60.0
        post_count = pre_count
        while time.time() < deadline:
            with psycopg.connect(load_config().postgres_url, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) AS n FROM graph_analysis_runs")
                    post_count = cur.fetchone()["n"]
            if post_count > pre_count:
                break
            time.sleep(2.0)
        assert post_count == pre_count + 1, (
            f"expected one new graph_analysis_runs row, got pre={pre_count} post={post_count}"
        )
    finally:
        uninstall_schedule()
        # Idempotent uninstall must not raise.
        result = uninstall_schedule()
        assert result.detail == "not installed"
