"""Install / uninstall the inbox watcher unit.

A thin descriptor builder over the ``compendium.service_unit`` seam: macOS gets a
LaunchAgent with ``WatchPaths`` (one per kind subdir); Linux gets a systemd user
``.path`` (one ``PathChanged=`` per kind) plus a oneshot ``.service``. Each
firing runs ``compendium inbox process --path <inbox>``. The seam owns rendering,
the launchctl / systemctl lifecycle, and platform dispatch.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from compendium import service_unit
from compendium.service_unit import (
    ServiceUnitError,
    UnitDescriptor,
    UnitResult,
    WatchPaths,
    launchd,
    systemd,
)

# Kinds match compendium.__main__._SOURCE_KINDS verbatim.
INBOX_KINDS: tuple[str, ...] = ("book", "article", "paper", "note", "web")
INBOX_LAYOUT: tuple[str, ...] = INBOX_KINDS + ("processed", "failed")

LABEL = "com.compendium.inbox"
LINUX_UNIT_BASENAME = "compendium-inbox"

# Back-compat aliases: the four services share one error and one result type.
InboxError = ServiceUnitError
InboxResult = UnitResult


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


def _descriptor(inbox_path: Path) -> UnitDescriptor:
    return UnitDescriptor(
        label=LABEL,
        linux_basename=LINUX_UNIT_BASENAME,
        program_args=_build_program_args(inbox_path),
        working_dir=_repo_root(),
        trigger=WatchPaths(tuple(f"{inbox_path}/{kind}" for kind in INBOX_KINDS)),
        service_description="Compendium inbox processor",
        log_basename="inbox",
        trigger_description="Compendium inbox watcher (PathChanged on every kind subdir)",
    )


def create_layout(path: Path) -> None:
    """Create the seven inbox subdirectories under ``path``. Idempotent."""
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    for sub in INBOX_LAYOUT:
        (path / sub).mkdir(exist_ok=True)


# --- render shims (consumed by tests) -------------------------------------


def _macos_plist_xml(inbox_path: Path) -> str:
    return launchd.render(_descriptor(inbox_path))


def _linux_service_unit(inbox_path: Path) -> str:
    return systemd.render_service(_descriptor(inbox_path))


def _linux_path_unit(inbox_path: Path) -> str:
    return systemd.render_trigger(_descriptor(inbox_path))


# --- public surface --------------------------------------------------------


def install_watcher(inbox_path: Path) -> InboxResult:
    """Install the per-OS inbox watcher unit watching ``inbox_path``."""
    inbox_path = inbox_path.expanduser().resolve()
    return service_unit.install(_descriptor(inbox_path))


def uninstall_watcher() -> InboxResult:
    """Remove the per-OS inbox watcher unit (idempotent)."""
    # Path content is irrelevant to uninstall (label / basename / trigger kind).
    return service_unit.uninstall(_descriptor(Path("/")))


def watcher_loaded() -> bool:
    """Return whether the inbox watcher unit is currently loaded."""
    return service_unit.loaded(_descriptor(Path("/")))
