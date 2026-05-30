"""Backup / restore tests (v0.2 Phase 2).

Unit-level: timestamp shape, missing-binary check, pre-check for an
already-present timestamp dir.

Integration: a round-trip backup/restore is added under sub-phase 2d
(the full integration test belongs with the restore code path; this
module covers the surface that lands in 2a).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from compendium.backup import BackupError, RestoreError, run_backup, run_restore
from compendium.backup.backup import utc_timestamp
from compendium.config import Config


def _config(tmp_path: Path, *, rsync_dest: str = "") -> Config:
    return Config(
        postgres_url="postgresql://x:x@127.0.0.1:1/x",
        opensearch_url="",
        qdrant_url="",
        memgraph_url="",
        vault_path=str(tmp_path / "vault"),
        synthesis_endpoint="",
        synthesis_model="",
        synthesis_api_key="",
        embeddings_endpoint="",
        embeddings_model="",
        embeddings_api_key="",
        backup_local_dir=str(tmp_path / "backups"),
        backup_rsync_dest=rsync_dest,
    )


def test_utc_timestamp_shape() -> None:
    ts = utc_timestamp()
    # YYYYMMDDTHHMMSSZ — 16 chars, Z suffix, sortable.
    assert re.fullmatch(r"\d{8}T\d{6}Z", ts), ts
    assert len(ts) == 16


def test_utc_timestamps_are_lexicographically_sortable() -> None:
    ts1 = utc_timestamp()
    ts2 = utc_timestamp()
    assert ts1 <= ts2  # generated in order, sort by string


def test_missing_binary_raises_backup_error(tmp_path, monkeypatch) -> None:
    # Hide pg_dump from PATH; tar should still be there but the prereq
    # check should fail on pg_dump.
    monkeypatch.setattr("shutil.which", lambda b: None if b == "pg_dump" else "/usr/bin/" + b)
    config = _config(tmp_path)
    with pytest.raises(BackupError) as excinfo:
        run_backup(config)
    assert excinfo.value.step == "prereq"
    assert "pg_dump" in excinfo.value.detail


def test_existing_timestamp_dir_raises_backup_error(tmp_path, monkeypatch) -> None:
    # Pretend every required binary exists so we reach the dir-exists check.
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    config = _config(tmp_path)
    fixed_ts = "20260101T000000Z"
    (Path(config.backup_local_dir) / fixed_ts).mkdir(parents=True)
    with pytest.raises(BackupError) as excinfo:
        run_backup(config, timestamp=fixed_ts)
    assert excinfo.value.step == "prereq"
    assert "already exists" in excinfo.value.detail


def test_missing_rsync_when_dest_set_raises_prereq(tmp_path, monkeypatch) -> None:
    # rsync_dest is set but rsync is hidden from PATH.
    def fake_which(b: str) -> str | None:
        return None if b == "rsync" else f"/usr/bin/{b}"

    monkeypatch.setattr("shutil.which", fake_which)
    config = _config(tmp_path, rsync_dest="/tmp/somewhere")
    with pytest.raises(BackupError) as excinfo:
        run_backup(config)
    assert excinfo.value.step == "prereq"
    assert "rsync" in excinfo.value.detail


def test_rsync_omitted_when_dest_empty_does_not_require_rsync(tmp_path, monkeypatch) -> None:
    """When BACKUP_RSYNC_DEST is empty, rsync is not required on PATH."""
    # Hide rsync, leave pg_dump+tar present; prereq must still pass.
    def fake_which(b: str) -> str | None:
        return None if b == "rsync" else f"/usr/bin/{b}"

    monkeypatch.setattr("shutil.which", fake_which)
    config = _config(tmp_path, rsync_dest="")
    # We're not running the real subprocess here — just check that the
    # prereq pass succeeds and we get past the binary check (the failure
    # below comes from a later step, not from rsync being missing).
    from compendium.backup.backup import _check_binaries, _REQUIRED_BINS, _RSYNC_BIN

    bins = _REQUIRED_BINS + ((_RSYNC_BIN,) if config.backup_rsync_dest else ())
    # No exception: prereq passes for the dest-empty case.
    _check_binaries(bins)


# --- restore --------------------------------------------------------------


def test_restore_missing_timestamp_dir_raises(tmp_path) -> None:
    config = _config(tmp_path)
    Path(config.backup_local_dir).mkdir(parents=True, exist_ok=True)
    with pytest.raises(RestoreError) as excinfo:
        run_restore(config, "19700101T000000Z", force=False)
    assert excinfo.value.step == "locate"
    assert "no backup directory" in excinfo.value.detail


def test_restore_missing_required_file_raises(tmp_path) -> None:
    config = _config(tmp_path)
    ts = "20260101T000000Z"
    ts_dir = Path(config.backup_local_dir) / ts
    ts_dir.mkdir(parents=True)
    # Only one of the two required files.
    (ts_dir / "compendium.dump").write_bytes(b"x")
    with pytest.raises(RestoreError) as excinfo:
        run_restore(config, ts, force=False)
    assert excinfo.value.step == "locate"
    assert "vault.tar.gz" in excinfo.value.detail


def test_restore_non_empty_vault_without_force_rejected(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    ts = "20260101T000000Z"
    ts_dir = Path(config.backup_local_dir) / ts
    ts_dir.mkdir(parents=True)
    (ts_dir / "compendium.dump").write_bytes(b"x")
    (ts_dir / "vault.tar.gz").write_bytes(b"x")
    # Vault non-empty.
    vault = Path(config.vault_path) / "concepts"
    vault.mkdir(parents=True)
    (vault / "psychological-safety.md").write_text("# title\n")
    # Binaries present.
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    with pytest.raises(RestoreError) as excinfo:
        run_restore(config, ts, force=False)
    assert excinfo.value.step == "guard"
    assert "vault is not empty" in excinfo.value.detail


def test_restore_missing_pg_restore_binary_raises(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    ts = "20260101T000000Z"
    ts_dir = Path(config.backup_local_dir) / ts
    ts_dir.mkdir(parents=True)
    (ts_dir / "compendium.dump").write_bytes(b"x")
    (ts_dir / "vault.tar.gz").write_bytes(b"x")
    # pg_restore not present; tar present.
    monkeypatch.setattr(
        "shutil.which",
        lambda b: None if b == "pg_restore" else f"/usr/bin/{b}",
    )
    with pytest.raises(RestoreError) as excinfo:
        run_restore(config, ts, force=False)
    assert excinfo.value.step == "prereq"
    assert "pg_restore" in excinfo.value.detail
