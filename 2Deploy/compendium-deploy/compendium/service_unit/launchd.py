"""macOS adapter: render a LaunchAgent plist for any :class:`Trigger`, and run
the ``launchctl`` bootout/bootstrap lifecycle through an injectable
:class:`Runner`. Reproduces, byte-for-byte, the plists the four service modules
generated before consolidation.
"""

from __future__ import annotations

import os
from pathlib import Path

from compendium.service_unit.descriptor import (
    AlwaysOn,
    Calendar,
    Interval,
    UnitDescriptor,
    WatchPaths,
)
from compendium.service_unit.errors import Probe, ServiceUnitError, UnitResult
from compendium.service_unit.runner import DEFAULT_RUNNER, Runner


def plist_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "compendium"


def _args_xml(args: list[str]) -> str:
    return "\n".join(f"        <string>{a}</string>" for a in args)


def _trigger_block(trigger: object) -> str:
    """The plist keys for a periodic / watched trigger (not AlwaysOn)."""
    if isinstance(trigger, Interval):
        return (
            "    <key>StartInterval</key>\n"
            f"    <integer>{trigger.seconds}</integer>\n"
        )
    if isinstance(trigger, Calendar):
        return (
            "    <key>StartCalendarInterval</key>\n"
            "    <dict>\n"
            "        <key>Hour</key>\n"
            f"        <integer>{trigger.hour}</integer>\n"
            "        <key>Minute</key>\n"
            f"        <integer>{trigger.minute}</integer>\n"
            "    </dict>\n"
        )
    if isinstance(trigger, WatchPaths):
        watch = "\n".join(f"        <string>{p}</string>" for p in trigger.paths)
        return "    <key>WatchPaths</key>\n    <array>\n" + watch + "\n    </array>\n"
    raise ServiceUnitError("render", f"no plist trigger block for {type(trigger).__name__}")


def _stdio_block(log_basename: str | None) -> str:
    if not log_basename:
        return ""
    d = log_dir()
    return (
        "    <key>StandardOutPath</key>\n"
        f"    <string>{d}/{log_basename}.out.log</string>\n"
        "    <key>StandardErrorPath</key>\n"
        f"    <string>{d}/{log_basename}.err.log</string>\n"
    )


def render(descriptor: UnitDescriptor) -> str:
    """Render the LaunchAgent plist for ``descriptor``."""
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{descriptor.label}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{_args_xml(descriptor.program_args)}\n"
        "    </array>\n"
        "    <key>WorkingDirectory</key>\n"
        f"    <string>{descriptor.working_dir}</string>\n"
    )
    if isinstance(descriptor.trigger, AlwaysOn):
        middle = (
            "    <key>RunAtLoad</key>\n"
            "    <true/>\n"
            "    <key>KeepAlive</key>\n"
            "    <true/>\n"
            f"{_stdio_block(descriptor.log_basename)}"
        )
    else:
        middle = (
            f"{_trigger_block(descriptor.trigger)}"
            f"{_stdio_block(descriptor.log_basename)}"
            "    <key>RunAtLoad</key>\n"
            "    <false/>\n"
        )
    return head + middle + "</dict>\n</plist>\n"


def install(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> UnitResult:
    plist = plist_path(descriptor.label)
    plist.parent.mkdir(parents=True, exist_ok=True)
    log_dir().mkdir(parents=True, exist_ok=True)
    plist.write_text(render(descriptor))

    uid = os.getuid()
    runner.run(["launchctl", "bootout", f"gui/{uid}", str(plist)])
    result = runner.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)])
    if result.returncode != 0:
        raise ServiceUnitError(
            "launchctl_bootstrap",
            (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    return UnitResult("install", plist, f"loaded {descriptor.label}{descriptor.detail_suffix}")


def uninstall(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> UnitResult:
    plist = plist_path(descriptor.label)
    uid = os.getuid()
    runner.run(["launchctl", "bootout", f"gui/{uid}", str(plist)])
    if plist.exists():
        plist.unlink()
        return UnitResult("uninstall", plist, "removed")
    return UnitResult("uninstall", plist, "not installed")


def probe(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> Probe:
    plist = plist_path(descriptor.label)
    if not plist.exists():
        return Probe(loaded=False, unit_path=plist, returncode=-1)
    uid = os.getuid()
    result = runner.run(["launchctl", "print", f"gui/{uid}/{descriptor.label}"])
    return Probe(
        loaded=result.returncode == 0,
        unit_path=plist,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
