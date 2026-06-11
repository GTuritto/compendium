"""Install / uninstall / status for the access-surface daemon.

A thin descriptor builder over the ``compendium.service_unit`` seam: unlike the
periodic services, the access surface is always-on, so it uses the
:class:`~compendium.service_unit.AlwaysOn` trigger — macOS ``RunAtLoad`` +
``KeepAlive``, Linux ``Restart=always`` into ``default.target``. The seam owns
rendering, the launchctl / systemctl lifecycle, and platform dispatch. The
status reader stays here because it surfaces serve-specific fields (host / port,
running state).

Closes the ADR-012 gap: the access surface is managed like backup / curate /
inbox. Posture stays localhost / no-auth (ADR-011); a non-loopback ``--host`` is
a v0.3 concern.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from compendium import service_unit
from compendium.service_unit import (
    AlwaysOn,
    DEFAULT_RUNNER,
    Runner,
    ServiceUnitError,
    UnitDescriptor,
    UnitResult,
    launchd,
    systemd,
)

LABEL = "com.compendium.serve"
LINUX_UNIT_BASENAME = "compendium-serve"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

# Back-compat aliases: the four services share one error and one result type.
ServiceError = ServiceUnitError
ServiceResult = UnitResult


@dataclass
class ServiceStatus:
    loaded: bool
    unit_path: Path
    state: str  # "running" | "not running" | "absent" | "unknown" | "unsupported platform"
    host: str | None
    port: int | None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["unit_path"] = str(self.unit_path)
        return d


def _repo_root() -> Path:
    # .../compendium/api/service.py -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


def _program_args(host: str, port: int) -> list[str]:
    uv = shutil.which("uv") or "uv"
    return [
        uv, "run", "--project", str(_repo_root()),
        "python", "-m", "compendium", "serve", "--host", host, "--port", str(port),
    ]


def _descriptor(host: str, port: int) -> UnitDescriptor:
    return UnitDescriptor(
        label=LABEL,
        linux_basename=LINUX_UNIT_BASENAME,
        program_args=_program_args(host, port),
        working_dir=_repo_root(),
        trigger=AlwaysOn(),
        service_description=f"Compendium access surface (HTTP, {host}:{port})",
        log_basename="serve",
        detail_suffix=f" on {host}:{port}",
    )


# --- render / path shims (consumed by status and tests) -------------------


def _macos_plist_xml(host: str, port: int) -> str:
    return launchd.render(_descriptor(host, port))


def _linux_service_unit(host: str, port: int) -> str:
    return systemd.render_service(_descriptor(host, port))


def _macos_plist_path() -> Path:
    return launchd.plist_path(LABEL)


def _linux_service_path() -> Path:
    return systemd.service_path(_descriptor(DEFAULT_HOST, DEFAULT_PORT))


def _parse_host_port(unit_text: str) -> tuple[str | None, int | None]:
    """Recover the configured host/port from a written unit, best-effort."""
    host: str | None = None
    port: int | None = None
    tokens = unit_text.replace("<string>", " ").replace("</string>", " ").split()
    for i, tok in enumerate(tokens):
        if i + 1 >= len(tokens):
            continue
        value = tokens[i + 1].strip("'\"")  # systemd ExecStart wraps args in quotes
        if tok == "--host":
            host = value
        elif tok == "--port":
            try:
                port = int(value)
            except ValueError:
                pass
    return host, port


# --- public surface ---------------------------------------------------------


def install_service(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ServiceResult:
    """Install the always-on access-surface unit (localhost, no auth)."""
    return service_unit.install(_descriptor(host, port))


def uninstall_service() -> ServiceResult:
    """Remove the access-surface unit (idempotent)."""
    return service_unit.uninstall(_descriptor(DEFAULT_HOST, DEFAULT_PORT))


# --- status (serve-specific: host / port + running state) -------------------
#
# The scheduler-CLI interaction lives behind service_unit.probe_activity
# (arch-status-probe-routing); this reader parses Probe.stdout and recovers
# the serve-specific fields (host/port) from the written unit file.


_LINUX_ACTIVE_RE = re.compile(r"Active:\s*(\S+)")


def read_status(*, runner: Runner = DEFAULT_RUNNER) -> ServiceStatus:
    """Current state of the access-surface unit; never raises."""
    try:
        plat = service_unit.platform()
    except ServiceUnitError:
        return ServiceStatus(False, Path("unknown"), "unsupported platform", None, None)

    probe = service_unit.probe_activity(_descriptor(DEFAULT_HOST, DEFAULT_PORT), runner=runner)
    if probe.returncode == -1 and not probe.stdout:
        return ServiceStatus(False, probe.unit_path, "absent", None, None)
    host, port = _parse_host_port(
        probe.unit_path.read_text() if probe.unit_path.exists() else ""
    )
    if plat == "darwin":
        if not probe.loaded:
            return ServiceStatus(False, probe.unit_path, "not running", host, port)
        state = "running" if ("state = running" in probe.stdout) else "not running"
        return ServiceStatus(True, probe.unit_path, state, host, port)
    active = _LINUX_ACTIVE_RE.search(probe.stdout)
    state = "running" if active and active.group(1) == "active" else "not running"
    return ServiceStatus(True, probe.unit_path, state, host, port)
