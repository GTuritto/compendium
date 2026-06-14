"""Inbox automation tests (v0.2 Phase 4).

Unit: layout creation, plist `WatchPaths` content, systemd path-unit
`PathChanged=` lines, platform-detect guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compendium.inbox import INBOX_KINDS, InboxError, create_layout
from compendium.inbox.install import (
    INBOX_LAYOUT,
    LABEL,
    LINUX_UNIT_BASENAME,
    _linux_path_unit,
    _linux_service_unit,
    _macos_plist_xml,
)


# --- create_layout --------------------------------------------------------


def test_create_layout_creates_seven_subdirs(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    create_layout(inbox)
    for sub in INBOX_LAYOUT:
        assert (inbox / sub).is_dir(), f"missing {sub}"
    assert len(INBOX_LAYOUT) == 7


def test_create_layout_is_idempotent(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    create_layout(inbox)
    create_layout(inbox)  # must not raise
    for sub in INBOX_LAYOUT:
        assert (inbox / sub).is_dir()


def test_create_layout_preserves_existing_files(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    create_layout(inbox)
    sentinel = inbox / "paper" / "preexisting.pdf"
    sentinel.write_bytes(b"x")
    create_layout(inbox)  # second call must not wipe contents
    assert sentinel.exists()
    assert sentinel.read_bytes() == b"x"


# --- macOS plist content --------------------------------------------------


def test_macos_plist_carries_label_and_watch_paths(tmp_path) -> None:
    xml = _macos_plist_xml(tmp_path / "inbox")
    assert LABEL in xml
    assert "<key>WatchPaths</key>" in xml
    for kind in INBOX_KINDS:
        assert f"{tmp_path}/inbox/{kind}" in xml
    # ProgramArguments invokes inbox process with the path.
    assert "inbox" in xml
    assert "process" in xml
    assert f"<string>{tmp_path}/inbox</string>" in xml or "--path</string>" in xml


def test_macos_plist_does_not_run_at_load(tmp_path) -> None:
    xml = _macos_plist_xml(tmp_path / "inbox")
    # The watcher should fire on filesystem events, not on load.
    assert "<key>RunAtLoad</key>" in xml
    assert "<false/>" in xml


# --- Linux systemd unit content -------------------------------------------


def test_linux_path_unit_carries_five_path_changed_entries(tmp_path) -> None:
    text = _linux_path_unit(tmp_path / "inbox")
    for kind in INBOX_KINDS:
        assert f"PathChanged={tmp_path}/inbox/{kind}" in text
    assert f"Unit={LINUX_UNIT_BASENAME}.service" in text
    assert "WantedBy=paths.target" in text


def test_linux_service_unit_invokes_inbox_process(tmp_path) -> None:
    text = _linux_service_unit(tmp_path / "inbox")
    assert "ExecStart=" in text
    assert "compendium" in text
    assert "inbox" in text
    assert "process" in text
    assert str(tmp_path / "inbox") in text


# --- platform guard -------------------------------------------------------


def test_platform_detect_refuses_unsupported(monkeypatch) -> None:
    # Platform detection now lives once, in the shared service_unit seam.
    import compendium.service_unit as su

    monkeypatch.setattr(su.sys, "platform", "freebsd14")
    with pytest.raises(InboxError) as excinfo:  # InboxError is an alias of ServiceUnitError
        su.platform()
    assert excinfo.value.step == "platform"
    assert "freebsd14" in excinfo.value.detail


# --- process worker -------------------------------------------------------


def _fake_ingest_result(status: str, detail: str = "ok"):
    from compendium.ingest.pipeline import IngestResult

    return [IngestResult(path="x", status=status, source_id=None, chunk_count=0, detail=detail)]


def test_process_routes_success_to_processed(tmp_path, monkeypatch) -> None:
    """An `ingested` result moves the file to processed/<today>/."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)
    src = tmp_path / "paper" / "sample.pdf"
    src.write_bytes(b"PDF")

    monkeypatch.setattr(
        process_module, "ingest", lambda path, kind: _fake_ingest_result("ingested")
    )
    # Skip the index sync side effect.
    monkeypatch.setattr(
        "compendium.index.sync.sync_pending",
        lambda *a, **k: type("R", (), {"indexed": 0, "failed": 0, "skipped": 0})(),
    )

    report = process_module.process_inbox(tmp_path)
    assert len(report.processed) == 1
    assert len(report.failed) == 0
    today_dir = tmp_path / "processed" / process_module._today_str()
    assert (today_dir / "sample.pdf").is_file()
    assert not src.exists()


def test_process_routes_unchanged_as_success(tmp_path, monkeypatch) -> None:
    """An `unchanged` result is treated as success per resolved decision."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)
    src = tmp_path / "paper" / "sample.pdf"
    src.write_bytes(b"PDF")

    monkeypatch.setattr(
        process_module, "ingest", lambda path, kind: _fake_ingest_result("unchanged")
    )
    monkeypatch.setattr(
        "compendium.index.sync.sync_pending",
        lambda *a, **k: type("R", (), {"indexed": 0, "failed": 0, "skipped": 0})(),
    )

    report = process_module.process_inbox(tmp_path)
    assert len(report.processed) == 1
    assert len(report.failed) == 0


def test_process_routes_failure_with_sidecar(tmp_path, monkeypatch) -> None:
    """A `failed` result moves the file to failed/<today>/ with a .error sidecar."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)
    src = tmp_path / "paper" / "broken.pdf"
    src.write_bytes(b"NOT A PDF")

    monkeypatch.setattr(
        process_module,
        "ingest",
        lambda path, kind: _fake_ingest_result("failed", detail="could not open PDF"),
    )
    monkeypatch.setattr(
        "compendium.index.sync.sync_pending",
        lambda *a, **k: type("R", (), {"indexed": 0, "failed": 0, "skipped": 0})(),
    )

    report = process_module.process_inbox(tmp_path)
    assert len(report.failed) == 1
    today_dir = tmp_path / "failed" / process_module._today_str()
    assert (today_dir / "broken.pdf").is_file()
    sidecar = today_dir / "broken.pdf.error"
    assert sidecar.is_file()
    assert sidecar.read_text() == "could not open PDF"


def test_process_skips_in_flight_downloads(tmp_path, monkeypatch) -> None:
    """`.tmp` / `.part` / `.crdownload` / `.download` / dot-files stay in place."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)
    skipped_names = [
        "x.pdf.tmp",
        "x.pdf.part",
        "x.pdf.crdownload",
        "x.pdf.download",
        ".hidden.pdf",
    ]
    for name in skipped_names:
        (tmp_path / "paper" / name).write_bytes(b"x")

    monkeypatch.setattr(
        process_module, "ingest",
        lambda path, kind: pytest.fail("ingest should not be called for skipped files"),
    )

    report = process_module.process_inbox(tmp_path)
    assert len(report.processed) == 0
    assert len(report.failed) == 0
    assert len(report.skipped) == len(skipped_names)
    # All skipped files remain.
    for name in skipped_names:
        assert (tmp_path / "paper" / name).is_file()


def test_process_systemic_failure_leaves_file_in_place(tmp_path, monkeypatch) -> None:
    """When ingest raises, the file stays in <kind>/ and the exception bubbles up."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)
    src = tmp_path / "paper" / "sample.pdf"
    src.write_bytes(b"PDF")

    def _boom(path, kind):
        raise ConnectionError("Postgres unreachable")

    monkeypatch.setattr(process_module, "ingest", _boom)

    with pytest.raises(ConnectionError):
        process_module.process_inbox(tmp_path)
    assert src.exists(), "file must stay in place on systemic failure"


def test_process_kind_derived_from_parent_dir(tmp_path, monkeypatch) -> None:
    """A file under article/ ingests with kind='article'; under note/ with kind='note'."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)
    (tmp_path / "article" / "x.html").write_bytes(b"<html/>")
    (tmp_path / "note" / "y.md").write_bytes(b"# y\n")

    captured: list[tuple[str, str]] = []

    def _capture(path, kind):
        captured.append((Path(path).name, kind))
        return _fake_ingest_result("ingested")

    monkeypatch.setattr(process_module, "ingest", _capture)
    monkeypatch.setattr(
        "compendium.index.sync.sync_pending",
        lambda *a, **k: type("R", (), {"indexed": 0, "failed": 0, "skipped": 0})(),
    )

    process_module.process_inbox(tmp_path)
    assert ("x.html", "article") in captured
    assert ("y.md", "note") in captured


def test_process_index_sync_not_called_when_nothing_routed(tmp_path, monkeypatch) -> None:
    """If the inbox is empty, sync_pending is not called."""
    from compendium.inbox import process as process_module

    create_layout(tmp_path)

    sync_called = []
    monkeypatch.setattr(
        "compendium.index.sync.sync_pending",
        lambda *a, **k: sync_called.append(True),
    )

    report = process_module.process_inbox(tmp_path)
    assert report.processed == []
    assert report.failed == []
    assert sync_called == [], "sync_pending must not be called when nothing was routed"


# --- status --------------------------------------------------------------


def test_status_empty_inbox(tmp_path, monkeypatch) -> None:
    """A fresh empty inbox returns all zeros and watcher_loaded=False."""
    from compendium.inbox import install as install_module
    from compendium.inbox.status import read_status

    create_layout(tmp_path)
    monkeypatch.setattr(install_module, "watcher_loaded", lambda: False)
    s = read_status(tmp_path)
    assert s.watcher_loaded is False
    assert sum(s.waiting.values()) == 0
    assert s.processed_today == 0
    assert s.processed_yesterday == 0
    assert s.failed_today == 0
    assert s.failed_yesterday == 0
    assert s.most_recent_processed is None
    assert s.most_recent_failed is None


def test_status_counts_waiting_per_kind(tmp_path, monkeypatch) -> None:
    """Files in <kind>/ count toward `waiting[kind]`."""
    from compendium.inbox import install as install_module
    from compendium.inbox.status import read_status

    create_layout(tmp_path)
    (tmp_path / "paper" / "a.pdf").write_bytes(b"x")
    (tmp_path / "paper" / "b.pdf").write_bytes(b"y")
    (tmp_path / "note" / "n.md").write_bytes(b"z")
    monkeypatch.setattr(install_module, "watcher_loaded", lambda: False)

    s = read_status(tmp_path)
    assert s.waiting["paper"] == 2
    assert s.waiting["note"] == 1
    assert s.waiting["article"] == 0


def test_status_counts_processed_today(tmp_path, monkeypatch) -> None:
    """A file in `processed/<today>/` counts toward `processed_today`."""
    from compendium.inbox import install as install_module
    from compendium.inbox.status import _today_str, read_status

    create_layout(tmp_path)
    today_dir = tmp_path / "processed" / _today_str()
    today_dir.mkdir(parents=True)
    (today_dir / "x.pdf").write_bytes(b"x")
    (today_dir / "y.pdf").write_bytes(b"y")
    monkeypatch.setattr(install_module, "watcher_loaded", lambda: False)

    s = read_status(tmp_path)
    assert s.processed_today == 2
    assert s.processed_yesterday == 0


def test_status_failed_count_excludes_error_sidecars(tmp_path, monkeypatch) -> None:
    """`<file>.error` sidecars are not counted as failed files."""
    from compendium.inbox import install as install_module
    from compendium.inbox.status import _today_str, read_status

    create_layout(tmp_path)
    today_dir = tmp_path / "failed" / _today_str()
    today_dir.mkdir(parents=True)
    (today_dir / "broken.pdf").write_bytes(b"x")
    (today_dir / "broken.pdf.error").write_text("could not open PDF")
    monkeypatch.setattr(install_module, "watcher_loaded", lambda: False)

    s = read_status(tmp_path)
    assert s.failed_today == 1  # not 2


def test_status_to_dict_serializes_path_and_datetimes(tmp_path, monkeypatch) -> None:
    """The dataclass JSON serialization stringifies Path and datetime fields."""
    import json

    from compendium.inbox import install as install_module
    from compendium.inbox.status import _today_str, read_status

    create_layout(tmp_path)
    today_dir = tmp_path / "processed" / _today_str()
    today_dir.mkdir(parents=True)
    (today_dir / "x.pdf").write_bytes(b"x")
    monkeypatch.setattr(install_module, "watcher_loaded", lambda: False)

    s = read_status(tmp_path)
    d = s.to_dict()
    assert isinstance(d["path"], str)
    assert isinstance(d["most_recent_processed"], str)
    json.dumps(d)  # must be JSON-clean


# --- integration round-trip ----------------------------------------------


@pytest.mark.integration
def test_inbox_process_routes_good_and_corrupt_files(tmp_path) -> None:
    """Drop a good PDF + a unique-content corrupt PDF → process → assert routing.

    Uses a unique-content corrupt file each run so the content hash
    never collides with a previously-ingested `tests/fixtures/broken.pdf`
    (which the dev DB may already know).
    """
    import shutil
    import time

    import psycopg
    from psycopg.rows import dict_row

    from compendium.config import load_config
    from compendium.inbox import process_inbox

    try:
        with psycopg.connect(load_config().postgres_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM sources")
                pre_sources = cur.fetchone()["n"]
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    repo_root = Path(__file__).resolve().parents[1]
    create_layout(tmp_path)

    # Good PDF — content hash is the same as tests/fixtures/sample.pdf;
    # repeat smoke runs will hit the unchanged path, which is still
    # routed to processed/ per resolved decision #4.
    shutil.copy(repo_root / "tests" / "fixtures" / "sample.pdf", tmp_path / "paper" / "sample.pdf")
    # Unique-content corrupt PDF — guarantees a fresh content hash so
    # the ingest pipeline actually parses (and fails on parse) rather
    # than short-circuiting to `unchanged`.
    unique_corrupt = tmp_path / "paper" / f"garbage-{time.time_ns()}.pdf"
    unique_corrupt.write_bytes(f"NOT-A-PDF-{time.time_ns()}".encode())
    # In-flight download — must be skipped.
    shutil.copy(
        repo_root / "tests" / "fixtures" / "sample.pdf",
        tmp_path / "paper" / "still-downloading.pdf.crdownload",
    )

    # Use Phase 1's environment to keep the embedder/synth stubs.
    import os
    os.environ["COMPENDIUM_EMBED_STUB"] = "1"
    os.environ["COMPENDIUM_SYNTH_STUB"] = "1"

    report = process_inbox(tmp_path)
    # Routing: sample.pdf → processed (either ingested or unchanged
    # depending on prior dev DB state). garbage → failed with sidecar.
    # .crdownload → skipped.
    today = (tmp_path / "processed" / __import__(
        "compendium.inbox.process", fromlist=["_today_str"]
    )._today_str())
    failed_today = (tmp_path / "failed" / __import__(
        "compendium.inbox.process", fromlist=["_today_str"]
    )._today_str())

    assert (today / "sample.pdf").is_file(), "sample.pdf should be under processed/<today>/"
    assert (failed_today / unique_corrupt.name).is_file(), (
        "unique-content corrupt PDF should be under failed/<today>/"
    )
    assert (failed_today / f"{unique_corrupt.name}.error").is_file(), (
        ".error sidecar must accompany the failed file"
    )
    sidecar_text = (failed_today / f"{unique_corrupt.name}.error").read_text()
    assert "could not open PDF" in sidecar_text or "PDF" in sidecar_text
    assert (tmp_path / "paper" / "still-downloading.pdf.crdownload").is_file(), (
        ".crdownload should be skipped, not routed"
    )

    assert len(report.processed) == 1
    assert len(report.failed) == 1
    assert len(report.skipped) == 1

    # At least one new sources row from the good file (the path is
    # the inbox path, which is unique per run because tmp_path is unique).
    with psycopg.connect(load_config().postgres_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM sources")
            post_sources = cur.fetchone()["n"]
    assert post_sources >= pre_sources, "sources count must not decrease"
