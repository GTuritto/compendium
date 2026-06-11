"""Read the per-OS scheduler state for the curate unit.

The scheduler-CLI interaction lives behind ``service_unit.probe_activity``
(arch-status-probe-routing): this module never shells out or dispatches
on the platform itself — it parses ``Probe.stdout`` with the schedule-specific
regexes (state, last-fired, next-fire, interval). Fields the scheduler does
not surface (for example, macOS does not report next-fire time) are returned
as ``None``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

from compendium import service_unit
from compendium.service_unit import DEFAULT_RUNNER, Probe, Runner, ServiceUnitError
from compendium.schedule.install import _descriptor


@dataclass
class ScheduleStatus:
    """Snapshot of the curate schedule's state."""

    loaded: bool
    unit_path: Path
    state: str  # human-readable: "running", "not running", "absent", "unknown"
    last_fired: str | None
    next_fire: str | None
    interval_seconds: int | None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["unit_path"] = str(self.unit_path)
        return d


def _bare(unit_path: Path, state: str, *, loaded: bool = False) -> ScheduleStatus:
    return ScheduleStatus(
        loaded=loaded, unit_path=unit_path, state=state,
        last_fired=None, next_fire=None, interval_seconds=None,
    )


def read_status(*, runner: Runner = DEFAULT_RUNNER) -> ScheduleStatus:
    """Return the current schedule status. Never raises — returns
    ``loaded=False`` when the unit is absent, the OS scheduler is
    unreachable, or the platform is unsupported.
    """
    try:
        plat = service_unit.platform()
    except ServiceUnitError:
        return _bare(Path("unknown"), "unsupported platform")

    descriptor = _descriptor(3600)  # label/paths only; the cadence is irrelevant to probing
    probe = service_unit.probe_activity(descriptor, runner=runner)
    if probe.returncode == -1 and not probe.stdout:
        return _bare(probe.unit_path, "absent")
    if plat == "darwin":
        return _macos_status(probe)
    return _linux_status(probe)


# --- macOS ----------------------------------------------------------------


_MACOS_STATE_RE = re.compile(r"state\s*=\s*(.+)")
_MACOS_LAST_EXIT_RE = re.compile(r"last exit code\s*=\s*(.+)")
_MACOS_INTERVAL_RE = re.compile(r"run interval\s*=\s*(\d+)\s*seconds")


def _macos_status(probe: Probe) -> ScheduleStatus:
    if not probe.loaded:
        return _bare(probe.unit_path, "not loaded")
    output = probe.stdout
    state_match = _MACOS_STATE_RE.search(output)
    last_match = _MACOS_LAST_EXIT_RE.search(output)
    interval_match = _MACOS_INTERVAL_RE.search(output)

    return ScheduleStatus(
        loaded=True,
        unit_path=probe.unit_path,
        state=state_match.group(1).strip() if state_match else "unknown",
        last_fired=last_match.group(1).strip() if last_match else None,
        next_fire=None,  # launchctl does not surface next-fire wall clock
        interval_seconds=int(interval_match.group(1)) if interval_match else None,
    )


# --- Linux ----------------------------------------------------------------


_LINUX_ACTIVE_RE = re.compile(r"Active:\s*(\S+)")
_LINUX_NEXT_RE = re.compile(r"Trigger:\s*(.+)")
_LINUX_LAST_RE = re.compile(r"Triggers:[\s\S]*?●\s*(\S[^\n]*)")
_LINUX_INTERVAL_RE = re.compile(r"OnUnitActiveSec=(\d+)")


def _linux_status(probe: Probe) -> ScheduleStatus:
    output = probe.stdout

    state = "unknown"
    active_match = _LINUX_ACTIVE_RE.search(output)
    if active_match:
        state = active_match.group(1).strip()

    next_fire = None
    next_match = _LINUX_NEXT_RE.search(output)
    if next_match:
        next_fire = next_match.group(1).strip()

    last_fired = None
    last_match = _LINUX_LAST_RE.search(output)
    if last_match:
        last_fired = last_match.group(1).strip()

    # The interval is authored into the timer unit file, not the CLI output.
    interval_seconds = None
    timer_text = probe.unit_path.read_text() if probe.unit_path.exists() else ""
    interval_match = _LINUX_INTERVAL_RE.search(timer_text)
    if interval_match:
        interval_seconds = int(interval_match.group(1))

    return ScheduleStatus(
        loaded=probe.loaded,
        unit_path=probe.unit_path,
        state=state,
        last_fired=last_fired,
        next_fire=next_fire,
        interval_seconds=interval_seconds,
    )
