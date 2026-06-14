"""Admin/ops surface invariants (ADR-020, v0.5).

Hermetic: the posture invariant (P1) is a source check; the one-seam invariant
(P3) monkeypatches the underlying CLI ops. The live render is exercised by the
manual smoke playbook (v0.5-adm.*).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_APP = _REPO_ROOT / "compendium" / "web" / "app.py"


def test_webui_exposes_no_destructive_ops():
    """TC-ADM-U1 / AC-ADM-1 (P1): the no-auth WebUI must not reference any
    destructive operation or unit management."""
    src = _WEB_APP.read_text(encoding="utf-8")
    # Specific call/import symbols, not prose words (the dashboard caption names
    # "delete, wipe, restore" as documentation of what is NOT here).
    forbidden = [
        "delete_source",
        "compendium.maintenance",
        "run_backup",
        "uninstall",
        "install_watcher",
        ".restore(",
    ]
    hits = [f for f in forbidden if f in src]
    assert not hits, f"WebUI must not reference destructive ops (ADR-020 P1): {hits}"


def test_provider_ops_route_to_the_cli_seam(monkeypatch):
    """TC-ADM-U2 / AC-ADM-4 (P3): the UI ops call the same functions the CLI
    uses, not copies."""
    from compendium.tui import data as provider

    seen: dict[str, object] = {}

    def fake_reindex(target):
        seen["reindex"] = target
        return "REINDEX"

    def fake_rebuild():
        seen["graph"] = True
        return "GRAPH"

    monkeypatch.setattr("compendium.index.sync.reindex", fake_reindex)
    monkeypatch.setattr("compendium.graph.rebuild.rebuild", fake_rebuild)

    assert provider.reindex_all() == "REINDEX"
    assert seen["reindex"] == "all"
    assert provider.graph_rebuild() == "GRAPH"
    assert seen["graph"] is True
    # the inbox recovery op exists and is callable on the same seam
    assert callable(provider.process_inbox)
