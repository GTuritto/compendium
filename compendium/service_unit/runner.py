"""The injectable subprocess seam the adapters shell out through.

The adapters never call ``subprocess.run`` directly: they call a :class:`Runner`.
The default :class:`SubprocessRunner` runs commands exactly as the four service
modules did (``capture_output=True, text=True, check=False``). Tests inject a
fake runner that records the argv and returns canned output, so the install /
uninstall / probe lifecycle is exercisable without a real launchctl / systemctl.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RunResult:
    """The subset of ``subprocess.CompletedProcess`` the adapters read."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    def run(self, args: list[str]) -> RunResult: ...


class SubprocessRunner:
    """The production runner: a thin wrapper over ``subprocess.run``."""

    def run(self, args: list[str]) -> RunResult:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")


DEFAULT_RUNNER: Runner = SubprocessRunner()
