"""Read the per-OS scheduler state for the curate unit.

macOS parses ``launchctl print gui/<uid>/com.compendium.curate``;
Linux parses ``systemctl --user list-timers --all compendium-curate.timer``
together with ``systemctl --user status compendium-curate.service``.
Fields the scheduler does not surface (for example, macOS does not
report next-fire time) are returned as ``None``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from compendium.schedule.install import (
    LABEL,
    LINUX_UNIT_BASENAME,
    _linux_service_path,
    _linux_timer_path,
    _macos_plist_path,
)


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


def read_status() -> ScheduleStatus:
    """Return the current schedule status. Never raises — returns
    ``loaded=False`` when the unit is absent or the OS scheduler is
    unreachable.
    """
    plat = sys.platform
    if plat == "darwin":
        return _macos_status()
    if plat.startswith("linux"):
        return _linux_status()
    return ScheduleStatus(
        loaded=False,
        unit_path=Path("unknown"),
        state="unsupported platform",
        last_fired=None,
        next_fire=None,
        interval_seconds=None,
    )


# --- macOS ----------------------------------------------------------------


_MACOS_STATE_RE = re.compile(r"state\s*=\s*(.+)")
_MACOS_LAST_EXIT_RE = re.compile(r"last exit code\s*=\s*(.+)")
_MACOS_INTERVAL_RE = re.compile(r"run interval\s*=\s*(\d+)\s*seconds")


def _macos_status() -> ScheduleStatus:
    plist = _macos_plist_path()
    if not plist.exists():
        return ScheduleStatus(
            loaded=False,
            unit_path=plist,
            state="absent",
            last_fired=None,
            next_fire=None,
            interval_seconds=None,
        )
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{LABEL}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return ScheduleStatus(
            loaded=False,
            unit_path=plist,
            state="not loaded",
            last_fired=None,
            next_fire=None,
            interval_seconds=None,
        )
    output = result.stdout
    state_match = _MACOS_STATE_RE.search(output)
    last_match = _MACOS_LAST_EXIT_RE.search(output)
    interval_match = _MACOS_INTERVAL_RE.search(output)

    return ScheduleStatus(
        loaded=True,
        unit_path=plist,
        state=state_match.group(1).strip() if state_match else "unknown",
        last_fired=last_match.group(1).strip() if last_match else None,
        next_fire=None,  # launchctl does not surface next-fire wall clock
        interval_seconds=int(interval_match.group(1)) if interval_match else None,
    )


# --- Linux ----------------------------------------------------------------


_LINUX_NEXT_RE = re.compile(r"Trigger:\s*(.+)")
_LINUX_LAST_RE = re.compile(r"Triggers:\s*\n\s*●\s*(.+)")  # rare; usually below
_LINUX_TIMER_LAST_RE = re.compile(r"^\s*LAST\s*=\s*(.+)", re.MULTILINE)


def _linux_status() -> ScheduleStatus:
    timer_path = _linux_timer_path()
    service_path = _linux_service_path()
    unit_path = timer_path if timer_path.exists() else service_path
    if not timer_path.exists():
        return ScheduleStatus(
            loaded=False,
            unit_path=timer_path,
            state="absent",
            last_fired=None,
            next_fire=None,
            interval_seconds=None,
        )

    # `systemctl --user status compendium-curate.timer` shows Active state,
    # ExecMainStartTimestamp, Trigger: timestamp.
    timer_status = subprocess.run(
        ["systemctl", "--user", "status", f"{LINUX_UNIT_BASENAME}.timer"],
        capture_output=True, text=True, check=False,
    )
    output = timer_status.stdout + "\n" + timer_status.stderr
    loaded = "Loaded:" in output and "could not be found" not in output

    state = "unknown"
    active_match = re.search(r"Active:\s*(\S+)", output)
    if active_match:
        state = active_match.group(1).strip()

    next_fire = None
    next_match = re.search(r"Trigger:\s*(.+)", output)
    if next_match:
        next_fire = next_match.group(1).strip()

    last_fired = None
    last_match = re.search(r"Triggers:[\s\S]*?●\s*(\S[^\n]*)", output)
    if last_match:
        last_fired = last_match.group(1).strip()

    # `list-timers` is a more reliable source of NEXT/LAST when populated.
    timers_list = subprocess.run(
        ["systemctl", "--user", "list-timers", "--all", f"{LINUX_UNIT_BASENAME}.timer"],
        capture_output=True, text=True, check=False,
    )
    list_output = timers_list.stdout
    if list_output:
        for line in list_output.splitlines():
            line = line.strip()
            if not line or line.startswith("NEXT") or line.startswith("---"):
                continue
            if LINUX_UNIT_BASENAME in line:
                # Columns: NEXT  LEFT  LAST  PASSED  UNIT  ACTIVATES
                cols = line.split()
                if len(cols) >= 6:
                    # NEXT is cols[0] + cols[1] + cols[2] (date + time + tz)
                    # Be defensive: just take the first three tokens as NEXT
                    # and the next three as LAST when present.
                    next_fire = next_fire or " ".join(cols[0:3])
                    if cols[3] not in ("n/a", "-"):
                        # LEFT is cols[3]; LAST starts at cols[4]
                        # The exact column count depends on output formatting;
                        # we already pulled NEXT, treat LAST as best-effort.
                        pass
                break

    interval_seconds = None
    timer_text = timer_path.read_text() if timer_path.exists() else ""
    interval_match = re.search(r"OnUnitActiveSec=(\d+)", timer_text)
    if interval_match:
        interval_seconds = int(interval_match.group(1))

    return ScheduleStatus(
        loaded=loaded,
        unit_path=timer_path,
        state=state,
        last_fired=last_fired,
        next_fire=next_fire,
        interval_seconds=interval_seconds,
    )
