"""The value object a service hands the ``service_unit`` seam, and the closed
``Trigger`` taxonomy that is the only axis varying between Compendium's four
OS-managed services (backup, curate, inbox, serve).

A service builds a :class:`UnitDescriptor` and calls ``service_unit.install`` /
``uninstall`` / ``probe``; everything else (plist / systemd rendering, file
paths, the launchctl / systemctl lifecycle, platform dispatch) lives behind the
seam. The descriptor carries the human-facing description strings and the macOS
log-file stem because those are data a caller declares, not logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# --- Trigger taxonomy ------------------------------------------------------
#
# A closed set of four cases. The adapter derives the unit *type* from the
# trigger: Interval / Calendar -> timer + companion service; WatchPaths -> path
# + companion service; AlwaysOn -> a single long-running service.


@dataclass(frozen=True)
class Interval:
    """Fire every ``seconds`` (macOS ``StartInterval``; Linux ``OnUnitActiveSec``)."""

    seconds: int


@dataclass(frozen=True)
class Calendar:
    """Fire daily at wall-clock ``hour:minute`` (macOS ``StartCalendarInterval``; Linux ``OnCalendar``)."""

    hour: int
    minute: int


@dataclass(frozen=True)
class WatchPaths:
    """Fire on a filesystem event under any of ``paths`` (macOS ``WatchPaths``; Linux ``.path``)."""

    paths: tuple[str, ...]


@dataclass(frozen=True)
class AlwaysOn:
    """A kept-alive daemon (macOS ``RunAtLoad`` + ``KeepAlive``; Linux ``Restart=always``)."""


Trigger = Interval | Calendar | WatchPaths | AlwaysOn


@dataclass(frozen=True)
class UnitDescriptor:
    """Everything the seam needs to install / uninstall / probe one unit.

    Fields:
        label: the launchd label and identity, e.g. ``com.compendium.curate``.
        linux_basename: the systemd unit-file stem, e.g. ``compendium-curate``.
        program_args: the command the unit runs when it fires.
        working_dir: the unit's working directory (repo root).
        trigger: how the unit fires (the only inter-service variation).
        service_description: ``[Unit] Description`` of the (companion) ``.service``.
        log_basename: macOS ``StandardOut/ErrPath`` stem (``<stem>.out.log``);
            ``None`` writes no redirect.
        trigger_description: ``[Unit] Description`` of the ``.timer`` / ``.path``
            unit; ``None`` for :class:`AlwaysOn` (no companion trigger unit).
        detail_suffix: appended to the install result detail (serve adds
            ``" on <host>:<port>"``); empty for the others.
    """

    label: str
    linux_basename: str
    program_args: list[str]
    working_dir: Path
    trigger: Trigger
    service_description: str
    log_basename: str | None = None
    trigger_description: str | None = None
    detail_suffix: str = ""
