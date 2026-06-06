"""Install / uninstall the scheduled ``curate run`` unit.

A thin descriptor builder over the ``compendium.service_unit`` seam: macOS gets a
LaunchAgent with ``StartInterval``; Linux gets a systemd user ``.timer``
(``OnUnitActiveSec`` + ``Persistent``) plus a oneshot ``.service``. The seam owns
the rendering, the launchctl / systemctl lifecycle, and platform dispatch.

The render and path helpers below are kept as thin shims because
``compendium/schedule/status.py`` and the existing tests reference them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from compendium import service_unit
from compendium.service_unit import Interval, ServiceUnitError, UnitDescriptor, UnitResult, launchd, systemd

LABEL = "com.compendium.curate"
LINUX_UNIT_BASENAME = "compendium-curate"

# Back-compat aliases: the four services now share one error and one result type.
ScheduleError = ServiceUnitError
ScheduleResult = UnitResult


def _repo_root() -> Path:
    # __file__ is .../compendium/schedule/install.py; root is two parents up.
    return Path(__file__).resolve().parents[2]


def _build_program_args() -> list[str]:
    """The command the unit invokes when it fires."""
    uv = shutil.which("uv") or "uv"
    return [uv, "run", "--project", str(_repo_root()), "python", "-m", "compendium", "curate", "run"]


def _descriptor(interval_seconds: int) -> UnitDescriptor:
    return UnitDescriptor(
        label=LABEL,
        linux_basename=LINUX_UNIT_BASENAME,
        program_args=_build_program_args(),
        working_dir=_repo_root(),
        trigger=Interval(interval_seconds),
        service_description="Compendium curation slow loop",
        log_basename="curate",
        trigger_description=f"Compendium curation slow-loop timer (every {interval_seconds}s)",
    )


# --- render / path shims (consumed by status.py and tests) ----------------


def _macos_plist_xml(interval_seconds: int) -> str:
    return launchd.render(_descriptor(interval_seconds))


def _macos_plist_path() -> Path:
    return launchd.plist_path(LABEL)


def _linux_service_unit() -> str:
    return systemd.render_service(_descriptor(0))


def _linux_timer_unit(interval_seconds: int) -> str:
    return systemd.render_trigger(_descriptor(interval_seconds))


def _linux_service_path() -> Path:
    return systemd.service_path(_descriptor(0))


def _linux_timer_path() -> Path:
    return systemd.trigger_unit_path(_descriptor(0))


# --- public surface --------------------------------------------------------


def install_schedule(interval_seconds: int) -> ScheduleResult:
    """Install the per-OS scheduled curate unit firing every ``interval_seconds``."""
    return service_unit.install(_descriptor(interval_seconds))


def uninstall_schedule() -> ScheduleResult:
    """Remove the per-OS scheduled curate unit (idempotent)."""
    return service_unit.uninstall(_descriptor(0))
