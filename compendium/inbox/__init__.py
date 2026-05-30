"""Inbox automation (v0.2 Phase 4).

Drop a file under ``<INBOX_PATH>/<kind>/`` and the OS-native
path-unit watcher (LaunchAgent on macOS, systemd user .path on
Linux) fires ``compendium inbox process``. The processor ingests
each eligible file via the existing pipeline with ``--kind <K>``
where ``K`` is the parent directory's name, and routes the file to
``processed/<YYYY-MM-DD>/`` or ``failed/<YYYY-MM-DD>/`` (with a
``<file>.error`` sidecar) by ingest result.

Public surface: :func:`install_watcher` / :func:`uninstall_watcher`
(this module — implemented in :mod:`compendium.inbox.install`),
:func:`process_inbox` (:mod:`compendium.inbox.process`),
:func:`read_status` (:mod:`compendium.inbox.status`).
"""

from compendium.inbox.install import (
    INBOX_KINDS,
    InboxError,
    InboxResult,
    create_layout,
    install_watcher,
    uninstall_watcher,
    watcher_loaded,
)
from compendium.inbox.process import ProcessReport, process_inbox
from compendium.inbox.status import InboxStatus, read_status

__all__ = [
    "INBOX_KINDS",
    "InboxError",
    "InboxResult",
    "InboxStatus",
    "ProcessReport",
    "create_layout",
    "install_watcher",
    "process_inbox",
    "read_status",
    "uninstall_watcher",
    "watcher_loaded",
]
