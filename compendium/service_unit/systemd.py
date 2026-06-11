"""Linux adapter: render the systemd user units for any :class:`Trigger` and
run the ``systemctl --user`` lifecycle through an injectable :class:`Runner`.

The trigger picks the unit shape: ``Interval`` / ``Calendar`` produce a
``.timer`` plus a oneshot companion ``.service``; ``WatchPaths`` produces a
``.path`` plus a oneshot ``.service``; ``AlwaysOn`` produces a single long-running
``.service``. Reproduces, byte-for-byte, the units the four service modules
generated before consolidation.
"""

from __future__ import annotations

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


def unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def enable_unit_name(descriptor: UnitDescriptor) -> str:
    """The unit systemctl enables: ``<basename>.timer`` / ``.path`` / ``.service``."""
    trigger = descriptor.trigger
    if isinstance(trigger, (Interval, Calendar)):
        suffix = "timer"
    elif isinstance(trigger, WatchPaths):
        suffix = "path"
    else:
        suffix = "service"
    return f"{descriptor.linux_basename}.{suffix}"


def service_path(descriptor: UnitDescriptor) -> Path:
    return unit_dir() / f"{descriptor.linux_basename}.service"


def trigger_unit_path(descriptor: UnitDescriptor) -> Path | None:
    """The ``.timer`` / ``.path`` file, or ``None`` for an :class:`AlwaysOn` service."""
    if isinstance(descriptor.trigger, AlwaysOn):
        return None
    return unit_dir() / enable_unit_name(descriptor)


def _primary_path(descriptor: UnitDescriptor) -> Path:
    return trigger_unit_path(descriptor) or service_path(descriptor)


# --- rendering -------------------------------------------------------------


def render_service(descriptor: UnitDescriptor) -> str:
    cmd = " ".join(descriptor.program_args)
    if isinstance(descriptor.trigger, AlwaysOn):
        return (
            "[Unit]\n"
            f"Description={descriptor.service_description}\n"
            "After=network.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={descriptor.working_dir}\n"
            f"ExecStart=/bin/sh -lc '{cmd}'\n"
            "Restart=always\n"
            "RestartSec=3\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
    return (
        "[Unit]\n"
        f"Description={descriptor.service_description}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={descriptor.working_dir}\n"
        f"ExecStart=/bin/sh -lc '{cmd}'\n"
    )


def render_trigger(descriptor: UnitDescriptor) -> str | None:
    """The ``.timer`` / ``.path`` unit text, or ``None`` for :class:`AlwaysOn`."""
    trigger = descriptor.trigger
    base = descriptor.linux_basename
    desc = descriptor.trigger_description
    if isinstance(trigger, Interval):
        return (
            "[Unit]\n"
            f"Description={desc}\n"
            "\n"
            "[Timer]\n"
            f"OnUnitActiveSec={trigger.seconds}\n"
            f"OnBootSec={trigger.seconds}\n"
            "Persistent=true\n"
            f"Unit={base}.service\n"
            "\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        )
    if isinstance(trigger, Calendar):
        return (
            "[Unit]\n"
            f"Description={desc}\n"
            "\n"
            "[Timer]\n"
            f"OnCalendar=*-*-* {trigger.hour:02d}:{trigger.minute:02d}:00\n"
            "Persistent=true\n"
            f"Unit={base}.service\n"
            "\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        )
    if isinstance(trigger, WatchPaths):
        path_changed = "\n".join(f"PathChanged={p}" for p in trigger.paths)
        return (
            "[Unit]\n"
            f"Description={desc}\n"
            "\n"
            "[Path]\n"
            f"{path_changed}\n"
            f"Unit={base}.service\n"
            "\n"
            "[Install]\n"
            "WantedBy=paths.target\n"
        )
    return None


# --- lifecycle -------------------------------------------------------------


def install(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> UnitResult:
    unit_dir().mkdir(parents=True, exist_ok=True)
    service_path(descriptor).write_text(render_service(descriptor))
    trigger_text = render_trigger(descriptor)
    if trigger_text is not None:
        trigger_unit_path(descriptor).write_text(trigger_text)  # type: ignore[union-attr]

    runner.run(["systemctl", "--user", "daemon-reload"])
    enable = enable_unit_name(descriptor)
    result = runner.run(["systemctl", "--user", "enable", "--now", enable])
    if result.returncode != 0:
        raise ServiceUnitError(
            "systemctl_enable",
            (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    return UnitResult("install", _primary_path(descriptor), f"enabled {enable}{descriptor.detail_suffix}")


def uninstall(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> UnitResult:
    enable = enable_unit_name(descriptor)
    runner.run(["systemctl", "--user", "disable", "--now", enable])
    candidates = [p for p in (trigger_unit_path(descriptor), service_path(descriptor)) if p is not None]
    removed: list[str] = []
    for path in candidates:
        if path.exists():
            path.unlink()
            removed.append(path.name)
    runner.run(["systemctl", "--user", "daemon-reload"])
    primary = _primary_path(descriptor)
    if removed:
        return UnitResult("uninstall", primary, f"removed {', '.join(removed)}")
    return UnitResult("uninstall", primary, "not installed")


def loaded(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> bool:
    primary = _primary_path(descriptor)
    if not primary.exists():
        return False
    result = runner.run(["systemctl", "--user", "is-enabled", enable_unit_name(descriptor)])
    return result.returncode == 0


def probe(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> Probe:
    primary = _primary_path(descriptor)
    if not primary.exists():
        return Probe(loaded=False, unit_path=primary, returncode=-1)
    result = runner.run(["systemctl", "--user", "is-enabled", enable_unit_name(descriptor)])
    return Probe(
        loaded=result.returncode == 0,
        unit_path=primary,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def probe_activity(descriptor: UnitDescriptor, *, runner: Runner = DEFAULT_RUNNER) -> Probe:
    """Scheduler-activity output for a status reader to parse.

    Runs ``systemctl --user status <enable-unit>`` and, for triggered units
    (timer/path), ``list-timers --all <unit>`` too; both outputs (stdout and
    stderr — systemd writes status text to either) are concatenated into
    ``Probe.stdout``. Field extraction stays in each service's status reader.
    """
    primary = _primary_path(descriptor)
    if not primary.exists():
        return Probe(loaded=False, unit_path=primary, returncode=-1)
    enable = enable_unit_name(descriptor)
    status = runner.run(["systemctl", "--user", "status", enable])
    out = status.stdout + "\n" + status.stderr
    if trigger_unit_path(descriptor) is not None:
        timers = runner.run(["systemctl", "--user", "list-timers", "--all", enable])
        out += "\n" + timers.stdout
    loaded = "Loaded:" in out and "could not be found" not in out
    return Probe(
        loaded=loaded,
        unit_path=primary,
        returncode=status.returncode,
        stdout=out,
        stderr=status.stderr,
    )
