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
