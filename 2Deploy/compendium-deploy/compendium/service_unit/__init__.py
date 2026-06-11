"""The one seam through which all four Compendium services (backup, curate,
inbox, serve) install, uninstall, and probe their OS-managed unit.

A service builds a :class:`UnitDescriptor` (its label, basename, program args,
working dir, and a :class:`Trigger`) and calls :func:`install` / :func:`uninstall`
/ :func:`loaded`. Platform is detected in exactly one place here; the launchd
(macOS) and systemd (Linux) adapters own all rendering and the launchctl /
systemctl lifecycle. One :class:`ServiceUnitError` replaces the four per-service
errors; rich status field-extraction (interval, next-fire, host:port) stays in
each service's status reader, which reads the unit paths and raw output exposed
here.

Implements ADR-012's posture (always-on personal-LAN units under launchd /
systemd); it does not change it.
"""

from __future__ import annotations

import sys

from compendium.service_unit import launchd, systemd
from compendium.service_unit.descriptor import (
    AlwaysOn,
    Calendar,
    Interval,
    Trigger,
    UnitDescriptor,
    WatchPaths,
)
from compendium.service_unit.errors import Probe, ServiceUnitError, UnitResult
from compendium.service_unit.runner import DEFAULT_RUNNER, RunResult, Runner, SubprocessRunner

__all__ = [
    "AlwaysOn",
    "Calendar",
    "Interval",
    "Probe",
    "RunResult",
    "Runner",
    "ServiceUnitError",
    "SubprocessRunner",
    "Trigger",
    "UnitDescriptor",
    "UnitResult",
    "WatchPaths",
    "install",
    "loaded",
    "platform",
    "probe",
    "probe_activity",
    "uninstall",
]


def platform() -> str:
    """``"darwin"`` or ``"linux"``; the single platform check for all services."""
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    raise ServiceUnitError("platform", f"unsupported platform: {sys.platform}")


def install(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> UnitResult:
    """Install ``descriptor`` as a per-OS unit and load it."""
    if platform() == "darwin":
        return launchd.install(descriptor, runner=runner)
    return systemd.install(descriptor, runner=runner)


def uninstall(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> UnitResult:
    """Remove ``descriptor``'s per-OS unit (idempotent)."""
    if platform() == "darwin":
        return launchd.uninstall(descriptor, runner=runner)
    return systemd.uninstall(descriptor, runner=runner)


def loaded(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> bool:
    """Whether the unit is present and loaded; never raises (False if unsupported)."""
    if sys.platform == "darwin":
        return launchd.probe(descriptor, runner=runner).loaded
    if sys.platform.startswith("linux"):
        return systemd.loaded(descriptor, runner=runner)
    return False


def probe(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> Probe:
    """Raw lifecycle-agnostic state for a service's status reader to parse."""
    if sys.platform == "darwin":
        return launchd.probe(descriptor, runner=runner)
    if sys.platform.startswith("linux"):
        return systemd.probe(descriptor, runner=runner)
    from pathlib import Path

    return Probe(loaded=False, unit_path=Path("unknown"), returncode=-1)


def probe_activity(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> Probe:
    """Scheduler-activity output (state / last / next fire) for a status reader.

    macOS reuses ``launchctl print`` (one command carries lifecycle and
    activity); Linux runs ``systemctl --user status`` plus ``list-timers``
    for triggered units. Readers parse ``Probe.stdout``; they never run the
    scheduler CLI themselves.
    """
    if sys.platform == "darwin":
        return launchd.probe(descriptor, runner=runner)
    if sys.platform.startswith("linux"):
        return systemd.probe_activity(descriptor, runner=runner)
    from pathlib import Path

    return Probe(loaded=False, unit_path=Path("unknown"), returncode=-1)
