"""Per-OS install / uninstall / status for the access-surface daemon.

Unlike the curate schedule (a timer that fires periodically), the access
surface is a long-running server: macOS uses a LaunchAgent with
``RunAtLoad=true`` + ``KeepAlive=true``; Linux uses a systemd user
``.service`` with ``Restart=always``, enabled into ``default.target`` so it
comes up on login/boot. Both run ``uv run --project <repo> python -m compendium
serve --host <host> --port <port>``.

Closes the ADR-012 gap: the access surface is now managed like backup / curate /
inbox. Posture stays localhost / no-auth (ADR-011); a non-loopback ``--host`` is
a v0.3 concern.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from compendium.logging import get_logger

LABEL = "com.compendium.serve"
LINUX_UNIT_BASENAME = "compendium-serve"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


class ServiceError(Exception):
    """Raised when the serve unit cannot be installed/removed."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


@dataclass
class ServiceResult:
    action: str
    path: Path
    detail: str = ""


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


def _platform() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    raise ServiceError("platform", f"unsupported platform: {sys.platform}")


def _repo_root() -> Path:
    # .../compendium/api/service.py -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


def _program_args(host: str, port: int) -> list[str]:
    uv = shutil.which("uv") or "uv"
    return [
        uv, "run", "--project", str(_repo_root()),
        "python", "-m", "compendium", "serve", "--host", host, "--port", str(port),
    ]


# --- macOS LaunchAgent ------------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _macos_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "compendium"


def _macos_plist_xml(host: str, port: int) -> str:
    log_dir = _macos_log_dir()
    args_xml = "\n".join(f"        <string>{a}</string>" for a in _program_args(host, port))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{_repo_root()}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/serve.out.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/serve.err.log</string>
</dict>
</plist>
"""


def _macos_install(host: str, port: int) -> ServiceResult:
    log = get_logger("compendium.serve")
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    _macos_log_dir().mkdir(parents=True, exist_ok=True)
    plist.write_text(_macos_plist_xml(host, port))
    log.info("serve plist written", path=str(plist), host=host, port=port)

    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist)],
                   capture_output=True, text=True, check=False)
    result = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ServiceError("launchctl_bootstrap",
                           (result.stderr or result.stdout or f"exit {result.returncode}").strip())
    log.info("serve loaded", label=LABEL)
    return ServiceResult("install", plist, f"loaded {LABEL} on {host}:{port}")


def _macos_uninstall() -> ServiceResult:
    log = get_logger("compendium.serve")
    plist = _macos_plist_path()
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist)],
                   capture_output=True, text=True, check=False)
    if plist.exists():
        plist.unlink()
        log.info("serve plist removed", path=str(plist))
        return ServiceResult("uninstall", plist, "removed")
    return ServiceResult("uninstall", plist, "not installed")


def _macos_status() -> ServiceStatus:
    plist = _macos_plist_path()
    if not plist.exists():
        return ServiceStatus(False, plist, "absent", None, None)
    host, port = _parse_host_port(plist.read_text())
    uid = os.getuid()
    out = subprocess.run(["launchctl", "print", f"gui/{uid}/{LABEL}"],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        return ServiceStatus(False, plist, "not running", host, port)
    state = "running" if ("state = running" in out.stdout) else "not running"
    return ServiceStatus(True, plist, state, host, port)


# --- Linux systemd user -----------------------------------------------------


def _linux_unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _linux_service_path() -> Path:
    return _linux_unit_dir() / f"{LINUX_UNIT_BASENAME}.service"


def _linux_service_unit(host: str, port: int) -> str:
    cmd = " ".join(_program_args(host, port))
    return f"""[Unit]
Description=Compendium access surface (HTTP, {host}:{port})
After=network.target

[Service]
Type=simple
WorkingDirectory={_repo_root()}
ExecStart=/bin/sh -lc '{cmd}'
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""


def _linux_install(host: str, port: int) -> ServiceResult:
    log = get_logger("compendium.serve")
    _linux_unit_dir().mkdir(parents=True, exist_ok=True)
    service = _linux_service_path()
    service.write_text(_linux_service_unit(host, port))
    subprocess.run(["systemctl", "--user", "daemon-reload"],
                   capture_output=True, text=True, check=False)
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{LINUX_UNIT_BASENAME}.service"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ServiceError("systemctl_enable",
                           (result.stderr or result.stdout or f"exit {result.returncode}").strip())
    log.info("serve enabled", service=f"{LINUX_UNIT_BASENAME}.service", host=host, port=port)
    return ServiceResult("install", service, f"enabled {LINUX_UNIT_BASENAME}.service on {host}:{port}")


def _linux_uninstall() -> ServiceResult:
    log = get_logger("compendium.serve")
    service = _linux_service_path()
    subprocess.run(["systemctl", "--user", "disable", "--now", f"{LINUX_UNIT_BASENAME}.service"],
                   capture_output=True, text=True, check=False)
    if service.exists():
        service.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True, text=True, check=False)
        log.info("serve unit removed", path=str(service))
        return ServiceResult("uninstall", service, "removed")
    return ServiceResult("uninstall", service, "not installed")


def _linux_status() -> ServiceStatus:
    service = _linux_service_path()
    if not service.exists():
        return ServiceStatus(False, service, "absent", None, None)
    host, port = _parse_host_port(service.read_text())
    active = subprocess.run(
        ["systemctl", "--user", "is-active", f"{LINUX_UNIT_BASENAME}.service"],
        capture_output=True, text=True, check=False,
    )
    state = "running" if active.stdout.strip() == "active" else "not running"
    return ServiceStatus(True, service, state, host, port)


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


# --- Public surface ---------------------------------------------------------


def install_service(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ServiceResult:
    """Install the always-on access-surface unit (localhost, no auth)."""
    return _macos_install(host, port) if _platform() == "darwin" else _linux_install(host, port)


def uninstall_service() -> ServiceResult:
    """Remove the access-surface unit (idempotent)."""
    return _macos_uninstall() if _platform() == "darwin" else _linux_uninstall()


def read_status() -> ServiceStatus:
    """Current state of the access-surface unit; never raises."""
    if sys.platform == "darwin":
        return _macos_status()
    if sys.platform.startswith("linux"):
        return _linux_status()
    return ServiceStatus(False, Path("unknown"), "unsupported platform", None, None)
