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


# --- schedule -------------------------------------------------------------


def test_parse_time_accepts_valid_24h() -> None:
    from compendium.backup.schedule import parse_time

    assert parse_time("02:00") == (2, 0)
    assert parse_time("23:59") == (23, 59)
    assert parse_time("0:00") == (0, 0)


def test_parse_time_rejects_invalid() -> None:
    from compendium.backup.schedule import ScheduleError, parse_time

    for bad in ("24:00", "12:60", "abc", "12", "12:5", "-1:00"):
        with pytest.raises(ScheduleError):
            parse_time(bad)


def test_macos_plist_xml_contains_calendar_interval() -> None:
    from compendium.backup.schedule import _macos_plist_xml, _LABEL

    xml = _macos_plist_xml(3, 15)
    assert _LABEL in xml
    assert "<integer>3</integer>" in xml
    assert "<integer>15</integer>" in xml
    assert "StartCalendarInterval" in xml
    assert "ProgramArguments" in xml


def test_linux_timer_unit_has_oncalendar() -> None:
    from compendium.backup.schedule import _linux_service_unit, _linux_timer_unit

    timer = _linux_timer_unit(3, 15)
    assert "OnCalendar=*-*-* 03:15:00" in timer
    assert "Persistent=true" in timer
    service = _linux_service_unit()
    assert "ExecStart=" in service
    assert "compendium" in service


# --- integration round-trip ----------------------------------------------


@pytest.mark.integration
def test_backup_restore_round_trip(tmp_path) -> None:
    """Back up a real test DB + vault, restore into a fresh DB, check rows + SHA-256s."""
    import hashlib
    import shutil as _shutil

    import psycopg
    from psycopg.rows import dict_row

    from compendium.backup import run_backup, run_restore
    from compendium.config import load_config

    if _shutil.which("pg_dump") is None or _shutil.which("pg_restore") is None:
        pytest.skip("pg_dump/pg_restore not on PATH; install libpq client tools")
    if _shutil.which("tar") is None:
        pytest.skip("tar not on PATH")

    base = load_config()
    admin_url = base.postgres_url.rsplit("/", 1)[0] + "/postgres"
    try:
        admin = psycopg.connect(admin_url, autocommit=True, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    src_name = "compendium_backup_src"
    dst_name = "compendium_backup_dst"
    try:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {src_name} WITH (FORCE)")
            cur.execute(f"DROP DATABASE IF EXISTS {dst_name} WITH (FORCE)")
            cur.execute(f"CREATE DATABASE {src_name}")
            cur.execute(f"CREATE DATABASE {dst_name}")
    finally:
        admin.close()

    # Run migrations against the source DB.
    repo_root = Path(__file__).resolve().parents[1]
    src_url = base.postgres_url.rsplit("/", 1)[0] + f"/{src_name}"
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))
    # env.py reads -x db_url before falling back to POSTGRES_URL.
    alembic_cfg.cmd_opts = type("ns", (), {"x": [f"db_url={src_url}"]})()
    command.upgrade(alembic_cfg, "head")

    # Seed one source row + one wiki_page row + one vault file.
    vault = tmp_path / "vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True)
    page_path = vault / "concepts" / "test-page.md"
    page_path.write_text("# Test Page\n\nbackup round-trip fixture.\n")
    page_sha_before = hashlib.sha256(page_path.read_bytes()).hexdigest()

    with psycopg.connect(src_url, autocommit=True, row_factory=dict_row) as conn:
        from compendium.db import repository

        repository.insert_source(
            conn, kind="note", title="Round-trip",
            content_hash="r" * 32 + "x" * 32, metadata={"k": "v"},
        )

    # Backup config pointing at the seeded DB and vault.
    src_config = type(base)(
        **{**base.__dict__,
           "postgres_url": src_url,
           "vault_path": str(vault),
           "backup_local_dir": str(tmp_path / "backups"),
           "backup_rsync_dest": ""}
    )
    backup_dir = run_backup(src_config)
    assert backup_dir.is_dir()
    assert (backup_dir / "compendium.dump").stat().st_size > 0
    assert (backup_dir / "vault.tar.gz").stat().st_size > 0

    # Source row count before destruction.
    with psycopg.connect(src_url, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM sources")
            src_count = cur.fetchone()["n"]
    assert src_count == 1

    # Wipe the vault and prepare the restore target.
    for md in vault.rglob("*.md"):
        md.unlink()
    dst_url = base.postgres_url.rsplit("/", 1)[0] + f"/{dst_name}"
    dst_config = type(base)(
        **{**base.__dict__,
           "postgres_url": dst_url,
           "vault_path": str(vault),
           "backup_local_dir": str(tmp_path / "backups"),
           "backup_rsync_dest": ""}
    )
    timestamp = backup_dir.name
    run_restore(dst_config, timestamp, force=False)

    # Row count on the destination matches the source.
    with psycopg.connect(dst_url, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM sources")
            dst_count = cur.fetchone()["n"]
    assert dst_count == src_count, f"dst rows {dst_count} != src rows {src_count}"

    # Vault file restored bit-identical.
    assert page_path.is_file(), "vault page missing after restore"
    page_sha_after = hashlib.sha256(page_path.read_bytes()).hexdigest()
    assert page_sha_after == page_sha_before, "vault file SHA-256 changed after restore"

    # Teardown.
    admin = psycopg.connect(admin_url, autocommit=True, row_factory=dict_row)
    try:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {src_name} WITH (FORCE)")
            cur.execute(f"DROP DATABASE IF EXISTS {dst_name} WITH (FORCE)")
    finally:
        admin.close()
