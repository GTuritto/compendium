"""``compendium backup`` — emit a timestamped pair, optionally rsync off-host.

Each invocation writes a directory ``<BACKUP_LOCAL_DIR>/<UTC-timestamp>/``
containing two files: ``compendium.dump`` (the output of
``pg_dump --format=custom``) and ``vault.tar.gz``. When
``BACKUP_RSYNC_DEST`` is set, the timestamped directory is mirrored to that
destination via ``rsync -a``. The function returns the local directory path
on success; raises :class:`BackupError` with a structured event on failure
and removes the partial local directory.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from compendium.config import Config
from compendium.logging import get_logger

_TIMESTAMP_FMT = "%Y%m%dT%H%M%SZ"
_DUMP_NAME = "compendium.dump"
_VAULT_NAME = "vault.tar.gz"
_REQUIRED_BINS = ("pg_dump", "tar")
_RSYNC_BIN = "rsync"


@dataclass
class BackupError(Exception):
    """A backup step failed. Carries the step name for structured reporting."""

    step: str
    detail: str
    local_dir: Path | None = None

    def __str__(self) -> str:
        return f"{self.step}: {self.detail}"


def utc_timestamp() -> str:
    """Return the current UTC timestamp in ``YYYYMMDDTHHMMSSZ`` format."""
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)


def _check_binaries(required: tuple[str, ...]) -> None:
    missing = [b for b in required if shutil.which(b) is None]
    if missing:
        raise BackupError(
            step="prereq",
            detail=f"required binaries not on PATH: {', '.join(missing)}",
        )


def _run(cmd: list[str], step: str) -> None:
    """Run a subprocess; raise BackupError on non-zero exit."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise BackupError(step=step, detail=str(exc)) from exc
    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        tail = stderr[-1] if stderr else f"exit {result.returncode}"
        raise BackupError(step=step, detail=tail)


def run_backup(config: Config, *, timestamp: str | None = None) -> Path:
    """Run a full backup. Returns the local timestamped directory.

    Raises:
        BackupError: on any failed step. The partial local directory is
            cleaned up except when the rsync step fails — the local backup
            is valid and worth keeping; only the off-host copy failed.
    """
    log = get_logger("compendium.backup")
    ts = timestamp or utc_timestamp()
    bins = _REQUIRED_BINS + ((_RSYNC_BIN,) if config.backup_rsync_dest else ())
    _check_binaries(bins)

    local_root = Path(config.backup_local_dir).expanduser().resolve()
    local_dir = local_root / ts
    if local_dir.exists():
        raise BackupError(
            step="prereq",
            detail=f"timestamped directory already exists: {local_dir}",
        )
    local_dir.mkdir(parents=True, exist_ok=False)

    try:
        log.info("backup start", timestamp=ts, local_dir=str(local_dir))

        dump_path = local_dir / _DUMP_NAME
        _run(
            [
                "pg_dump",
                "--format=custom",
                "-f", str(dump_path),
                config.postgres_url,
            ],
            step="pg_dump",
        )
        log.info("backup pg_dump", path=str(dump_path), bytes=dump_path.stat().st_size)

        vault_path = Path(config.vault_path).expanduser().resolve()
        if not vault_path.is_dir():
            raise BackupError(step="tar", detail=f"vault path not a directory: {vault_path}")
        tar_path = local_dir / _VAULT_NAME
        _run(
            [
                "tar",
                "-czf", str(tar_path),
                "-C", str(vault_path.parent),
                vault_path.name,
            ],
            step="tar",
        )
        log.info("backup tar", path=str(tar_path), bytes=tar_path.stat().st_size)
    except Exception:
        shutil.rmtree(local_dir, ignore_errors=True)
        raise

    if config.backup_rsync_dest:
        dest = config.backup_rsync_dest.rstrip("/")
        # For local destinations (no `host:` prefix), ensure the parent
        # directory exists so rsync does not error on a missing root.
        # Remote destinations are the operator's responsibility — the
        # operational doc names that contract.
        if ":" not in dest and not dest.startswith(("rsync://", "ssh://")):
            try:
                Path(dest).expanduser().mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                local_err = BackupError(
                    step="rsync_mkdir",
                    detail=str(exc),
                    local_dir=local_dir,
                )
                log.error("backup rsync_mkdir failed", detail=str(exc))
                raise local_err from exc
        try:
            _run(
                [
                    "rsync",
                    "-a",
                    f"{local_dir}/",
                    f"{dest}/{ts}/",
                ],
                step="rsync",
            )
            log.info("backup rsync", dest=f"{dest}/{ts}/")
        except BackupError as exc:
            # Local backup is valid; keep it. Raise with the local path so
            # the caller can report success-but-rsync-failed cleanly.
            exc.local_dir = local_dir
            log.error("backup rsync failed", local_dir=str(local_dir), detail=exc.detail)
            raise

    log.info("backup complete", timestamp=ts, local_dir=str(local_dir))
    return local_dir
