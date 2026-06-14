"""Read the inbox's current snapshot from the filesystem.

No database, no inbox-state table — the filesystem is the source of
truth. Reports the resolved inbox path, the watcher unit's loaded
state (delegated to ``compendium.inbox.install``), per-kind waiting
counts, processed_today / processed_yesterday counts, failed_today /
failed_yesterday counts, and the timestamps of the most recent
processed and failed files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from compendium.inbox import install


@dataclass
class InboxStatus:
    """Snapshot of the inbox's current state, derived from disk."""

    path: Path
    watcher_loaded: bool
    waiting: dict[str, int] = field(default_factory=dict)
    processed_today: int = 0
    processed_yesterday: int = 0
    failed_today: int = 0
    failed_yesterday: int = 0
    most_recent_processed: datetime | None = None
    most_recent_failed: datetime | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        d["most_recent_processed"] = (
            self.most_recent_processed.isoformat() if self.most_recent_processed else None
        )
        d["most_recent_failed"] = (
            self.most_recent_failed.isoformat() if self.most_recent_failed else None
        )
        return d


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _yesterday_str() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def _count_eligible(directory: Path) -> int:
    """Count files (not subdirs, not sidecars) under ``directory``."""
    if not directory.is_dir():
        return 0
    count = 0
    for entry in directory.iterdir():
        if entry.is_file() and not entry.name.endswith(".error"):
            count += 1
    return count


def _most_recent_mtime(parent: Path) -> datetime | None:
    """Return the most recent mtime across the dated children of ``parent``."""
    if not parent.is_dir():
        return None
    latest: float | None = None
    for dated in parent.iterdir():
        if not dated.is_dir():
            continue
        for entry in dated.iterdir():
            if entry.is_file() and not entry.name.endswith(".error"):
                m = entry.stat().st_mtime
                if latest is None or m > latest:
                    latest = m
    return datetime.fromtimestamp(latest, tz=timezone.utc) if latest else None


def read_status(path: Path) -> InboxStatus:
    """Return the inbox's filesystem-derived snapshot."""
    path = path.expanduser().resolve()
    today = _today_str()
    yesterday = _yesterday_str()

    waiting: dict[str, int] = {}
    for kind in install.INBOX_KINDS:
        waiting[kind] = _count_eligible(path / kind)

    return InboxStatus(
        path=path,
        watcher_loaded=install.watcher_loaded(),
        waiting=waiting,
        processed_today=_count_eligible(path / "processed" / today),
        processed_yesterday=_count_eligible(path / "processed" / yesterday),
        failed_today=_count_eligible(path / "failed" / today),
        failed_yesterday=_count_eligible(path / "failed" / yesterday),
        most_recent_processed=_most_recent_mtime(path / "processed"),
        most_recent_failed=_most_recent_mtime(path / "failed"),
    )
