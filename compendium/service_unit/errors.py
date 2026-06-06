"""Shared value types for the ``service_unit`` seam: the one error, the install
/ uninstall result, and the status probe. Kept in their own module so the two
adapters (``launchd``, ``systemd``) and the package surface can import them
without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ServiceUnitError(Exception):
    """An OS-service lifecycle step failed or was rejected.

    Replaces the four per-service errors (``ScheduleError`` x2, ``InboxError``,
    ``ServiceError``). The ``step`` vocabulary is preserved verbatim
    (``platform``, ``launchctl_bootstrap``, ``systemctl_enable``, ...).
    """

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


@dataclass
class UnitResult:
    """Outcome of an install / uninstall, suitable for printing."""

    action: str
    path: Path
    detail: str = ""


@dataclass
class Probe:
    """The raw lifecycle-agnostic state of a unit, for a service's status verb
    to extract its own fields from. ``loaded`` reflects whether the scheduler
    reports the unit present; ``stdout`` / ``stderr`` are the raw scheduler-CLI
    output the service parses for interval / next-fire / host:port / etc.
    """

    loaded: bool
    unit_path: Path
    returncode: int
    stdout: str = ""
    stderr: str = ""
