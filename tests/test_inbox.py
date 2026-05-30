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
    assert f"<string>{tmp_path}/inbox</string>" in xml or f"--path</string>" in xml


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
    from compendium.inbox import install as install_module

    monkeypatch.setattr(install_module.sys, "platform", "freebsd14")
    with pytest.raises(InboxError) as excinfo:
        install_module._platform()
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
