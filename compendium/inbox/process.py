"""``compendium inbox process`` — scan inbox, ingest, route.

For each eligible file under ``<inbox>/<kind>/``, call the existing
``compendium.ingest.pipeline.ingest()`` with the kind derived from the
parent directory. Route by ingest result:

- ``ingested`` / ``updated`` / ``unchanged`` → move to
  ``<inbox>/processed/<YYYY-MM-DD>/<file>``;
- ``failed`` → move to ``<inbox>/failed/<YYYY-MM-DD>/<file>``; write a
  sidecar ``<file>.error`` carrying the ``detail`` string;
- raised exception (Postgres unreachable, etc.) → leave the file in
  place and re-raise so the watcher exit code surfaces the systemic
  failure.

The atomic move is ``Path.rename()``. Concurrent watcher fires that
race on the same file resolve by losing the race on a
``FileNotFoundError``.

After the per-file loop, when at least one file was routed, run one
``compendium index sync`` to drain the indexing queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from compendium.inbox.install import INBOX_KINDS
from compendium.ingest.pipeline import ingest
from compendium.logging import get_logger

_SKIP_SUFFIXES: tuple[str, ...] = (".tmp", ".part", ".crdownload", ".download")


@dataclass
class ProcessReport:
    """Outcome of one ``process_inbox`` invocation."""

    processed: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    errored: bool = False

    def __str__(self) -> str:
        return (
            f"processed={len(self.processed)} "
            f"failed={len(self.failed)} "
            f"skipped={len(self.skipped)}"
        )


def _is_eligible(file: Path) -> bool:
    name = file.name
    if name.startswith("."):
        return False
    for suffix in _SKIP_SUFFIXES:
        if name.endswith(suffix):
            return False
    return file.is_file()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _route(
    file: Path, parent_dest: Path, error_detail: str | None = None
) -> Path | None:
    """Move ``file`` into ``parent_dest/<YYYY-MM-DD>/``. Return the new
    path on success, ``None`` on lost-race.

    When ``error_detail`` is provided, also write a sidecar
    ``<file>.error`` in the same dated directory.
    """
    dated = parent_dest / _today_str()
    dated.mkdir(parents=True, exist_ok=True)
    target = dated / file.name
    try:
        file.rename(target)
    except FileNotFoundError:
        return None
    if error_detail is not None:
        sidecar = target.with_suffix(target.suffix + ".error")
        sidecar.write_text(error_detail)
    return target


def process_inbox(inbox: Path) -> ProcessReport:
    """Scan the inbox, ingest each eligible file, route by result.

    Raises:
        Exception: re-raises any non-``IngestResult.failed`` exception
            from the ingest pipeline so the caller can surface the
            systemic failure to the OS scheduler (which then retries
            on the next event).
    """
    log = get_logger("compendium.inbox.process")
    inbox = inbox.expanduser().resolve()
    report = ProcessReport()
    routed_any = False

    for kind in INBOX_KINDS:
        kind_dir = inbox / kind
        if not kind_dir.is_dir():
            continue
        for file in sorted(kind_dir.iterdir()):
            if not _is_eligible(file):
                if file.is_file():
                    report.skipped.append(file)
                continue

            try:
                results = ingest(str(file), kind=kind)
            except Exception:
                report.errored = True
                log.error(
                    "inbox systemic failure",
                    file=str(file),
                    kind=kind,
                )
                raise

            # ingest() always returns a non-empty list for a single
            # file; take the first result.
            result = results[0]
            if result.status == "failed":
                target = _route(file, inbox / "failed", error_detail=result.detail)
                if target is None:
                    log.info("inbox race lost", file=str(file))
                    continue
                report.failed.append((target, result.detail))
                log.info(
                    "inbox routed failed",
                    file=str(target),
                    detail=result.detail,
                )
                routed_any = True
            else:
                # ingested | updated | unchanged → success
                target = _route(file, inbox / "processed")
                if target is None:
                    log.info("inbox race lost", file=str(file))
                    continue
                report.processed.append(target)
                log.info(
                    "inbox routed processed",
                    file=str(target),
                    status=result.status,
                )
                routed_any = True

    # Drain the indexing queue once after the per-file loop, only when
    # at least one file was routed (success or parse-fail).
    if routed_any:
        try:
            from compendium.index.sync import sync_pending

            stats = sync_pending()
            log.info(
                "inbox index sync",
                indexed=stats.indexed,
                failed=stats.failed,
                skipped=stats.skipped,
            )
        except Exception as exc:  # pragma: no cover - logged, not raised
            log.warning("inbox index sync failed", error=str(exc))

    return report
