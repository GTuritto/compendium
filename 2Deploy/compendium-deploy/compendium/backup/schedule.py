"""Install / uninstall the scheduled ``compendium backup`` unit.

A thin descriptor builder over the ``compendium.service_unit`` seam: macOS gets a
LaunchAgent with ``StartCalendarInterval`` (daily at ``HH:MM``); Linux gets a
systemd user ``.timer`` (``OnCalendar``) plus a oneshot ``.service``. The default
firing time is 02:00 local; ``--at HH:MM`` overrides. The seam owns rendering,
the launchctl / systemctl lifecycle, and platform dispatch.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from compendium import service_unit
from compendium.service_unit import Calendar, ServiceUnitError, UnitDescriptor, UnitResult, launchd, systemd

_LABEL = "com.compendium.backup"
_LINUX_UNIT_BASENAME = "compendium-backup"
_TIME_PATTERN = re.compile(r"^([0-1]?\d|2[0-3]):([0-5]\d)$")

# Back-compat aliases: the four services share one error and one result type.
ScheduleError = ServiceUnitError
ScheduleResult = UnitResult


def parse_time(value: str) -> tuple[int, int]:
    """Parse ``HH:MM`` 24-hour into ``(hour, minute)``. Raises on bad input."""
    match = _TIME_PATTERN.match(value)
    if not match:
        raise ScheduleError(
            step="parse",
            detail=f"expected HH:MM (24-hour), got '{value}'",
        )
    return int(match.group(1)), int(match.group(2))


def _repo_root() -> Path:
    # __file__ is .../compendium/backup/schedule.py; root is two parents up.
    return Path(__file__).resolve().parents[2]


def _build_program_args() -> list[str]:
    """The command the unit invokes when it fires."""
    uv = shutil.which("uv") or "uv"
    return [uv, "run", "--project", str(_repo_root()), "python", "-m", "compendium", "backup"]


def _descriptor(hour: int, minute: int) -> UnitDescriptor:
    return UnitDescriptor(
        label=_LABEL,
        linux_basename=_LINUX_UNIT_BASENAME,
        program_args=_build_program_args(),
        working_dir=_repo_root(),
        trigger=Calendar(hour, minute),
        service_description="Compendium backup (PostgreSQL + vault)",
        log_basename="backup",
        trigger_description=f"Daily Compendium backup at {hour:02d}:{minute:02d}",
    )


# --- render shims (consumed by tests) -------------------------------------


def _macos_plist_xml(hour: int, minute: int) -> str:
    return launchd.render(_descriptor(hour, minute))


def _linux_service_unit() -> str:
    return systemd.render_service(_descriptor(0, 0))


def _linux_timer_unit(hour: int, minute: int) -> str:
    return systemd.render_trigger(_descriptor(hour, minute))


# --- public surface --------------------------------------------------------


def install_schedule(at: str = "02:00") -> ScheduleResult:
    """Install the per-OS scheduled backup unit firing daily at ``at`` (``HH:MM``)."""
    hour, minute = parse_time(at)
    return service_unit.install(_descriptor(hour, minute))


def uninstall_schedule() -> ScheduleResult:
    """Remove the per-OS scheduled backup unit (idempotent)."""
    return service_unit.uninstall(_descriptor(0, 0))


__all__ = [
    "ScheduleError",
    "ScheduleResult",
    "install_schedule",
    "parse_time",
    "uninstall_schedule",
]
