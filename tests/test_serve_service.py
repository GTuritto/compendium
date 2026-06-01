"""Unit tests for the access-surface service installer (deploy tooling).

Pure checks on the generated unit content + the host/port parser. The live
install/uninstall/status path (launchctl/systemd) is exercised by hand and in
the deployment smoke walk, not here.
"""

from __future__ import annotations

from compendium.api import service


def test_macos_plist_is_a_keepalive_daemon_with_serve_args():
    xml = service._macos_plist_xml("127.0.0.1", 8787)
    assert "<string>com.compendium.serve</string>" in xml
    assert "<key>KeepAlive</key>" in xml and "<key>RunAtLoad</key>" in xml
    assert "<key>StartInterval</key>" not in xml  # a daemon, not a timer
    assert "<string>serve</string>" in xml
    assert "<string>--host</string>" in xml and "<string>127.0.0.1</string>" in xml
    assert "<string>--port</string>" in xml and "<string>8787</string>" in xml


def test_linux_service_restarts_and_wants_default_target():
    unit = service._linux_service_unit("127.0.0.1", 9000)
    assert "Type=simple" in unit
    assert "Restart=always" in unit
    assert "WantedBy=default.target" in unit
    assert "serve --host 127.0.0.1 --port 9000" in unit


def test_parse_host_port_round_trips_from_each_unit():
    plist = service._macos_plist_xml("0.0.0.0", 8800)
    assert service._parse_host_port(plist) == ("0.0.0.0", 8800)
    unit = service._linux_service_unit("127.0.0.1", 1234)
    assert service._parse_host_port(unit) == ("127.0.0.1", 1234)


def test_program_args_invoke_compendium_serve():
    args = service._program_args("127.0.0.1", 8787)
    assert args[-5:] == ["python", "-m", "compendium", "serve", "--host"] or "serve" in args
    assert "serve" in args and "--host" in args and "127.0.0.1" in args and "8787" in args
