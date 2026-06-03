"""Per-OS install / uninstall for the curate schedule.

macOS writes ``~/Library/LaunchAgents/com.compendium.curate.plist``
with ``StartInterval=<seconds>`` and loads via
``launchctl bootstrap``. Linux writes
``~/.config/systemd/user/compendium-curate.{service,timer}`` with
``OnUnitActiveSec=<seconds>`` + ``Persistent=true`` and enables via
``systemctl --user enable --now``.

Both branches invoke ``uv run --project <repo> python -m compendium
curate run`` per fire.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from compendium.logging import get_logger
from compendium.schedule.cadence import ScheduleError

LABEL = "com.compendium.curate"
LINUX_UNIT_BASENAME = "compendium-curate"


@dataclass
class ScheduleResult:
    """Outcome of an install / uninstall, suitable for printing."""

    action: str
    path: Path
    detail: str = ""


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
    # __file__ is .../compendium/schedule/install.py; root is two parents up.
    return Path(__file__).resolve().parents[2]


def _build_program_args() -> list[str]:
    """The command the unit invokes when it fires."""
    uv = shutil.which("uv") or "uv"
    return [uv, "run", "--project", str(_repo_root()), "python", "-m", "compendium", "curate", "run"]


# --- macOS LaunchAgent ----------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _macos_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "compendium"


def _macos_plist_xml(interval_seconds: int) -> str:
    log_dir = _macos_log_dir()
    program_args = _build_program_args()
    args_xml = "\n".join(f"        <string>{a}</string>" for a in program_args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{_repo_root()}</string>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>StandardOutPath</key>
    <string>{log_dir}/curate.out.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/curate.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def _macos_install(interval_seconds: int) -> ScheduleResult:
    log = get_logger("compendium.schedule")
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    _macos_log_dir().mkdir(parents=True, exist_ok=True)
    plist.write_text(_macos_plist_xml(interval_seconds))
    log.info("schedule plist written", path=str(plist), interval_seconds=interval_seconds)

    uid = os.getuid()
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
    log.info("schedule loaded", label=LABEL)
    return ScheduleResult(action="install", path=plist, detail=f"loaded {LABEL}")


def _macos_uninstall() -> ScheduleResult:
    log = get_logger("compendium.schedule")
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
    return _linux_unit_dir() / f"{LINUX_UNIT_BASENAME}.service"


def _linux_timer_path() -> Path:
    return _linux_unit_dir() / f"{LINUX_UNIT_BASENAME}.timer"


def _linux_service_unit() -> str:
    cmd = " ".join(_build_program_args())
    return f"""[Unit]
Description=Compendium curation slow loop

[Service]
Type=oneshot
WorkingDirectory={_repo_root()}
ExecStart=/bin/sh -lc '{cmd}'
"""


def _linux_timer_unit(interval_seconds: int) -> str:
    return f"""[Unit]
Description=Compendium curation slow-loop timer (every {interval_seconds}s)

[Timer]
OnUnitActiveSec={interval_seconds}
OnBootSec={interval_seconds}
Persistent=true
Unit={LINUX_UNIT_BASENAME}.service

[Install]
WantedBy=timers.target
"""


def _linux_install(interval_seconds: int) -> ScheduleResult:
    log = get_logger("compendium.schedule")
    unit_dir = _linux_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = _linux_service_path()
    timer = _linux_timer_path()
    service.write_text(_linux_service_unit())
    timer.write_text(_linux_timer_unit(interval_seconds))
    log.info("schedule units written", service=str(service), timer=str(timer))

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, text=True, check=False,
    )
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{LINUX_UNIT_BASENAME}.timer"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ScheduleError(
            step="systemctl_enable",
            detail=(result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    log.info("schedule enabled", timer=f"{LINUX_UNIT_BASENAME}.timer")
    return ScheduleResult(
        action="install",
        path=timer,
        detail=f"enabled {LINUX_UNIT_BASENAME}.timer",
    )


def _linux_uninstall() -> ScheduleResult:
    log = get_logger("compendium.schedule")
    timer = _linux_timer_path()
    service = _linux_service_path()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{LINUX_UNIT_BASENAME}.timer"],
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


def install_schedule(interval_seconds: int) -> ScheduleResult:
    """Install the per-OS scheduled curate unit firing every ``interval_seconds``."""
    plat = _platform()
    if plat == "darwin":
        return _macos_install(interval_seconds)
    return _linux_install(interval_seconds)


def uninstall_schedule() -> ScheduleResult:
    """Remove the per-OS scheduled curate unit (idempotent)."""
    plat = _platform()
    if plat == "darwin":
        return _macos_uninstall()
    return _linux_uninstall()
