"""Scheduled curation (v0.2 Phase 3).

The slow curation loop runs on a schedule under launchd (macOS) or
systemd user timers (Linux). `compendium schedule install` writes the
unit and registers it; `compendium schedule uninstall` removes it
idempotently; `compendium schedule status` reports loaded state and
last/next firings. Each firing invokes `compendium curate run`.

This module ships the v0.2 interim per ADR-012: a per-OS timer
fires the CLI. The long-term home for in-process scheduling is
Phase 7's access-surface daemon.
"""

from compendium.schedule.cadence import ScheduleError, parse_interval
from compendium.schedule.install import (
    ScheduleResult,
    install_schedule,
    uninstall_schedule,
)
from compendium.schedule.status import ScheduleStatus, read_status

__all__ = [
    "ScheduleError",
    "ScheduleResult",
    "ScheduleStatus",
    "install_schedule",
    "parse_interval",
    "read_status",
    "uninstall_schedule",
]
