"""Per-OS install / uninstall for the inbox watcher.

macOS writes ``~/Library/LaunchAgents/com.compendium.inbox.plist``
with ``WatchPaths`` listing each ``<kind>/`` subdir and loads via
``launchctl bootstrap``. Linux writes
``~/.config/systemd/user/compendium-inbox.{path,service}`` with
five ``PathChanged=`` entries and enables via
``systemctl --user enable --now``.

Both branches invoke ``uv run --project <repo> python -m compendium
inbox process --path <inbox>`` per file-system event.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from compendium.logging import get_logger

# Kinds match compendium.__main__._SOURCE_KINDS verbatim.
INBOX_KINDS: tuple[str, ...] = ("book", "article", "paper", "note", "web")
INBOX_LAYOUT: tuple[str, ...] = INBOX_KINDS + ("processed", "failed")

LABEL = "com.compendium.inbox"
LINUX_UNIT_BASENAME = "compendium-inbox"


class InboxError(Exception):
    """An inbox step failed or was rejected by a guard."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


@dataclass
class InboxResult:
    """Outcome of an install / uninstall, suitable for printing."""

    action: str
    path: Path
    detail: str = ""


def _platform() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    raise InboxError(
        step="platform",
        detail=f"unsupported platform: {sys.platform}",
    )


def _repo_root() -> Path:
    # __file__ is .../compendium/inbox/install.py; root is two parents up.
    return Path(__file__).resolve().parents[2]


def _build_program_args(inbox_path: Path) -> list[str]:
    """The command the unit invokes when it fires."""
    uv = shutil.which("uv") or "uv"
    return [
        uv, "run", "--project", str(_repo_root()),
        "python", "-m", "compendium", "inbox", "process",
        "--path", str(inbox_path),
    ]


def create_layout(path: Path) -> None:
    """Create the seven inbox subdirectories under ``path``. Idempotent."""
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    for sub in INBOX_LAYOUT:
        (path / sub).mkdir(exist_ok=True)


# --- macOS LaunchAgent ----------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _macos_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "compendium"


def _macos_plist_xml(inbox_path: Path) -> str:
    log_dir = _macos_log_dir()
    program_args = _build_program_args(inbox_path)
    args_xml = "\n".join(f"        <string>{a}</string>" for a in program_args)
    watch_xml = "\n".join(
        f"        <string>{inbox_path}/{kind}</string>" for kind in INBOX_KINDS
    )
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
    <key>WatchPaths</key>
    <array>
{watch_xml}
    </array>
    <key>StandardOutPath</key>
    <string>{log_dir}/inbox.out.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/inbox.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def _macos_install(inbox_path: Path) -> InboxResult:
    log = get_logger("compendium.inbox")
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    _macos_log_dir().mkdir(parents=True, exist_ok=True)
    plist.write_text(_macos_plist_xml(inbox_path))
    log.info("inbox plist written", path=str(plist), inbox=str(inbox_path))

    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist)],
        capture_output=True, text=True, check=False,
    )
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise InboxError(
            step="launchctl_bootstrap",
            detail=(result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    log.info("inbox watcher loaded", label=LABEL)
    return InboxResult(action="install", path=plist, detail=f"loaded {LABEL}")


def _macos_uninstall() -> InboxResult:
    log = get_logger("compendium.inbox")
    plist = _macos_plist_path()
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist)],
        capture_output=True, text=True, check=False,
    )
    if plist.exists():
        plist.unlink()
        log.info("inbox plist removed", path=str(plist))
        return InboxResult(action="uninstall", path=plist, detail="removed")
    log.info("inbox plist absent", path=str(plist))
    return InboxResult(action="uninstall", path=plist, detail="not installed")


def _macos_watcher_loaded() -> bool:
    plist = _macos_plist_path()
    if not plist.exists():
        return False
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{LABEL}"],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


# --- Linux systemd user ---------------------------------------------------


def _linux_unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _linux_path_unit_path() -> Path:
    return _linux_unit_dir() / f"{LINUX_UNIT_BASENAME}.path"


def _linux_service_path() -> Path:
    return _linux_unit_dir() / f"{LINUX_UNIT_BASENAME}.service"


def _linux_service_unit(inbox_path: Path) -> str:
    cmd = " ".join(_build_program_args(inbox_path))
    return f"""[Unit]
Description=Compendium inbox processor

[Service]
Type=oneshot
WorkingDirectory={_repo_root()}
ExecStart=/bin/sh -lc '{cmd}'
"""


def _linux_path_unit(inbox_path: Path) -> str:
    path_changed = "\n".join(
        f"PathChanged={inbox_path}/{kind}" for kind in INBOX_KINDS
    )
    return f"""[Unit]
Description=Compendium inbox watcher (PathChanged on every kind subdir)

[Path]
{path_changed}
Unit={LINUX_UNIT_BASENAME}.service

[Install]
WantedBy=paths.target
"""


def _linux_install(inbox_path: Path) -> InboxResult:
    log = get_logger("compendium.inbox")
    unit_dir = _linux_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = _linux_service_path()
    path_unit = _linux_path_unit_path()
    service.write_text(_linux_service_unit(inbox_path))
    path_unit.write_text(_linux_path_unit(inbox_path))
    log.info(
        "inbox units written",
        service=str(service),
        path_unit=str(path_unit),
    )

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, text=True, check=False,
    )
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{LINUX_UNIT_BASENAME}.path"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise InboxError(
            step="systemctl_enable",
            detail=(result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
    log.info("inbox watcher enabled", path_unit=f"{LINUX_UNIT_BASENAME}.path")
    return InboxResult(
        action="install",
        path=path_unit,
        detail=f"enabled {LINUX_UNIT_BASENAME}.path",
    )


def _linux_uninstall() -> InboxResult:
    log = get_logger("compendium.inbox")
    path_unit = _linux_path_unit_path()
    service = _linux_service_path()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{LINUX_UNIT_BASENAME}.path"],
        capture_output=True, text=True, check=False,
    )
    removed = []
    for path in (path_unit, service):
        if path.exists():
            path.unlink()
            removed.append(path.name)
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, text=True, check=False,
    )
    if removed:
        log.info("inbox units removed", paths=removed)
        return InboxResult(
            action="uninstall",
            path=path_unit,
            detail=f"removed {', '.join(removed)}",
        )
    log.info("inbox units absent")
    return InboxResult(action="uninstall", path=path_unit, detail="not installed")


def _linux_watcher_loaded() -> bool:
    if not _linux_path_unit_path().exists():
        return False
    result = subprocess.run(
        ["systemctl", "--user", "is-enabled", f"{LINUX_UNIT_BASENAME}.path"],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


# --- Public surface --------------------------------------------------------


def install_watcher(inbox_path: Path) -> InboxResult:
    """Install the per-OS inbox watcher unit watching ``inbox_path``."""
    plat = _platform()
    inbox_path = inbox_path.expanduser().resolve()
    if plat == "darwin":
        return _macos_install(inbox_path)
    return _linux_install(inbox_path)


def uninstall_watcher() -> InboxResult:
    """Remove the per-OS inbox watcher unit (idempotent)."""
    plat = _platform()
    if plat == "darwin":
        return _macos_uninstall()
    return _linux_uninstall()


def watcher_loaded() -> bool:
    """Return whether the inbox watcher unit is currently loaded."""
    try:
        plat = _platform()
    except InboxError:
        return False
    if plat == "darwin":
        return _macos_watcher_loaded()
    return _linux_watcher_loaded()
