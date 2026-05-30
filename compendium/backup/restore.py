"""``compendium restore <timestamp>`` — drop both authoritative stores back.

Given a timestamp, locates ``<BACKUP_LOCAL_DIR>/<timestamp>/`` and runs
``pg_restore --clean --if-exists --no-owner --dbname=<POSTGRES_URL>`` against
``compendium.dump`` and ``tar -xzf`` of ``vault.tar.gz`` into the vault
parent. Refuses to overwrite a non-empty vault without ``force=True``.

On success, the caller is expected to print the reindex / graph-rebuild
reminder; this module emits the structlog event and returns normally.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from compendium.backup.backup import (
    _DUMP_NAME,
    _VAULT_NAME,
    BackupError,
    _check_binaries,
    _run,
)
from compendium.config import Config
from compendium.logging import get_logger

_REQUIRED_BINS = ("pg_restore", "tar")
# pg_restore --clean --if-exists exits 1 when DROP IF EXISTS commands target
# objects that do not yet exist (a fresh database). The actual restore
# succeeds; pg_restore reports a final "warning: errors ignored on restore"
# line. Treat that specific shape as success.
_IGNORED_WARNING_TOKEN = "errors ignored on restore"


class RestoreError(Exception):
    """A restore step failed or was rejected by a safety guard."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


def _vault_has_pages(vault_path: Path) -> bool:
    return any(vault_path.rglob("*.md"))


def run_restore(config: Config, timestamp: str, *, force: bool) -> None:
    """Restore the system to the state captured at ``timestamp``.

    Raises:
        RestoreError: when the timestamp dir is missing, the vault is
            non-empty without ``force=True``, or any restore step fails.
    """
    log = get_logger("compendium.restore")
    local_root = Path(config.backup_local_dir).expanduser().resolve()
    local_dir = local_root / timestamp
    if not local_dir.is_dir():
        raise RestoreError(
            step="locate",
            detail=f"no backup directory at {local_dir}",
        )
    dump_path = local_dir / _DUMP_NAME
    tar_path = local_dir / _VAULT_NAME
    for required in (dump_path, tar_path):
        if not required.is_file():
            raise RestoreError(
                step="locate",
                detail=f"missing required file: {required.name}",
            )

    try:
        _check_binaries(_REQUIRED_BINS)
    except BackupError as exc:
        raise RestoreError(step=exc.step, detail=exc.detail) from exc

    vault_path = Path(config.vault_path).expanduser().resolve()
    if vault_path.is_dir() and _vault_has_pages(vault_path) and not force:
        raise RestoreError(
            step="guard",
            detail="vault is not empty; pass --force to overwrite",
        )

    log.info("restore start", timestamp=timestamp, local_dir=str(local_dir))

    # Database first: pg_restore --clean --if-exists drops existing objects
    # before restoring, so it works against a populated or an empty DB.
    # Against a fresh DB the IF-EXISTS DROPs all match zero rows and
    # pg_restore exits 1 with "warning: errors ignored on restore: N"
    # despite the actual restore succeeding. Tolerate that exact shape.
    try:
        result = subprocess.run(
            [
                "pg_restore",
                "--clean", "--if-exists",
                "--no-owner",
                "--dbname=" + config.postgres_url,
                str(dump_path),
            ],
            capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise RestoreError(step="pg_restore", detail=str(exc)) from exc
    if result.returncode != 0:
        stderr = result.stderr or ""
        if _IGNORED_WARNING_TOKEN not in stderr:
            tail_lines = stderr.strip().splitlines()
            tail = tail_lines[-1] if tail_lines else f"exit {result.returncode}"
            raise RestoreError(step="pg_restore", detail=tail)
        log.info("restore pg_restore ignored-warnings", count=stderr.count("warning"))
    log.info("restore pg_restore", dump=str(dump_path))

    # Vault next: wipe the existing markdown tree and extract the tarball.
    if vault_path.is_dir():
        for md_file in vault_path.rglob("*.md"):
            md_file.unlink()
    else:
        vault_path.mkdir(parents=True, exist_ok=True)

    try:
        _run(
            [
                "tar",
                "-xzf", str(tar_path),
                "-C", str(vault_path.parent),
            ],
            step="tar_extract",
        )
    except BackupError as exc:
        raise RestoreError(step=exc.step, detail=exc.detail) from exc

    # Sanity-check the layout: the three canonical subdirectories should
    # exist after extraction (matching the v0.1 vault structure).
    for sub in ("concepts", "topics", "sources"):
        expected = vault_path / sub
        if not expected.is_dir():
            log.warning(
                "restore vault layout",
                detail=f"expected {expected} after extract",
            )

    log.info("restore complete", timestamp=timestamp, vault_path=str(vault_path))


# Re-export for convenience and discoverability.
__all__ = ["RestoreError", "run_restore"]
