"""Per-OS schedule install / uninstall for ``compendium backup``.

macOS uses a LaunchAgent plist under ``~/Library/LaunchAgents/``;
Linux uses a systemd user service + timer under
``~/.config/systemd/user/``. The default firing time is daily at
02:00 local; ``compendium backup install --at HH:MM`` overrides.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from compendium.logging import get_logger

_LABEL = "com.compendium.backup"
_LINUX_UNIT_BASENAME = "compendium-backup"
_TIME_PATTERN = re.compile(r"^([0-1]?\d|2[0-3]):([0-5]\d)$")


class ScheduleError(Exception):
    """A schedule install / uninstall step failed or was rejected."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


@dataclass
class ScheduleResult:
    """The outcome of an install / uninstall, suitable for printing."""

    action: str
    path: Path
    detail: str = ""


def parse_time(value: str) -> tuple[int, int]:
    """Parse ``HH:MM`` 24-hour into ``(hour, minute)``. Raises on bad input."""
    match = _TIME_PATTERN.match(value)
    if not match:
        raise ScheduleError(
            step="parse",
            detail=f"expected HH:MM (24-hour), got '{value}'",
        )
    return int(match.group(1)), int(match.group(2))


def _platform() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    raise ScheduleError(
        step="platform",
        detail=f"unsupported platform: {sys.platform}",
    )


def _repo_root() -> Path:
    # __file__ is .../compendium/backup/schedule.py; root is two parents up.
    return Path(__file__).resolve().parents[2]


def _build_program_args() -> list[str]:
    """The command the unit invokes when it fires."""
    uv = shutil.which("uv") or "uv"
    return [uv, "run", "--project", str(_repo_root()), "python", "-m", "compendium", "backup"]


# --- macOS LaunchAgent ----------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _macos_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "compendium"


def _macos_plist_xml(hour: int, minute: int) -> str:
    log_dir = _macos_log_dir()
    program_args = _build_program_args()
    args_xml = "\n".join(f"        <string>{a}</string>" for a in program_args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{_repo_root()}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/backup.out.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/backup.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def _macos_install(hour: int, minute: int) -> ScheduleResult:
    log = get_logger("compendium.backup.schedule")
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    _macos_log_dir().mkdir(parents=True, exist_ok=True)
    plist.write_text(_macos_plist_xml(hour, minute))
    log.info("schedule plist written", path=str(plist), hour=hour, minute=minute)

    uid = os.getuid()
    # Try bootout first (no-op if not loaded), then bootstrap.
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist)],
        capture_output=True, text=True, check=False,
    )
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ScheduleError(
            step="launchctl_bootstrap",
            detail=(result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    log.info("schedule loaded", label=_LABEL)
    return ScheduleResult(action="install", path=plist, detail=f"loaded {_LABEL}")


def _macos_uninstall() -> ScheduleResult:
    log = get_logger("compendium.backup.schedule")
    plist = _macos_plist_path()
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist)],
        capture_output=True, text=True, check=False,
    )
    if plist.exists():
        plist.unlink()
        log.info("schedule plist removed", path=str(plist))
        return ScheduleResult(action="uninstall", path=plist, detail="removed")
    log.info("schedule plist absent", path=str(plist))
    return ScheduleResult(action="uninstall", path=plist, detail="not installed")


# --- Linux systemd user ---------------------------------------------------


def _linux_unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _linux_service_path() -> Path:
    return _linux_unit_dir() / f"{_LINUX_UNIT_BASENAME}.service"


def _linux_timer_path() -> Path:
    return _linux_unit_dir() / f"{_LINUX_UNIT_BASENAME}.timer"


def _linux_service_unit() -> str:
    cmd = " ".join(_build_program_args())
    return f"""[Unit]
Description=Compendium backup (PostgreSQL + vault)

[Service]
Type=oneshot
WorkingDirectory={_repo_root()}
ExecStart=/bin/sh -lc '{cmd}'
"""


def _linux_timer_unit(hour: int, minute: int) -> str:
    return f"""[Unit]
Description=Daily Compendium backup at {hour:02d}:{minute:02d}

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true
Unit={_LINUX_UNIT_BASENAME}.service

[Install]
WantedBy=timers.target
"""


def _linux_install(hour: int, minute: int) -> ScheduleResult:
    log = get_logger("compendium.backup.schedule")
    unit_dir = _linux_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = _linux_service_path()
    timer = _linux_timer_path()
    service.write_text(_linux_service_unit())
    timer.write_text(_linux_timer_unit(hour, minute))
    log.info("schedule units written", service=str(service), timer=str(timer))

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, text=True, check=False,
    )
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{_LINUX_UNIT_BASENAME}.timer"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ScheduleError(
            step="systemctl_enable",
            detail=(result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    log.info("schedule enabled", timer=f"{_LINUX_UNIT_BASENAME}.timer")
    return ScheduleResult(
        action="install",
        path=timer,
        detail=f"enabled {_LINUX_UNIT_BASENAME}.timer",
    )


def _linux_uninstall() -> ScheduleResult:
    log = get_logger("compendium.backup.schedule")
    timer = _linux_timer_path()
    service = _linux_service_path()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{_LINUX_UNIT_BASENAME}.timer"],
        capture_output=True, text=True, check=False,
    )
    removed = []
    for path in (timer, service):
        if path.exists():
            path.unlink()
            removed.append(path.name)
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, text=True, check=False,
    )
    if removed:
        log.info("schedule units removed", paths=removed)
        return ScheduleResult(
            action="uninstall",
            path=timer,
            detail=f"removed {', '.join(removed)}",
        )
    log.info("schedule units absent")
    return ScheduleResult(action="uninstall", path=timer, detail="not installed")


# --- Public surface --------------------------------------------------------


def install_schedule(at: str = "02:00") -> ScheduleResult:
    """Install the per-OS scheduled backup unit firing daily at ``at`` (``HH:MM``)."""
    hour, minute = parse_time(at)
    plat = _platform()
    if plat == "darwin":
        return _macos_install(hour, minute)
    return _linux_install(hour, minute)


def uninstall_schedule() -> ScheduleResult:
    """Remove the per-OS scheduled backup unit (idempotent)."""
    plat = _platform()
    if plat == "darwin":
        return _macos_uninstall()
    return _linux_uninstall()


__all__ = [
    "ScheduleError",
    "ScheduleResult",
    "install_schedule",
    "parse_time",
    "uninstall_schedule",
]
