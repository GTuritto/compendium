"""Page list screen with filters and a synth action (Phase 8c)."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from compendium.tui import data as tui_data
from compendium.tui.screens.widgets import FormModal

_KIND_CYCLE = [None, "source", "concept", "topic"]
_STATUS_CYCLE = [None, "draft", "canonical", "deprecated"]


class PagesScreen(Screen):
    """Wiki pages; ``k``/``t`` cycle kind/status filters, ``y`` synths, ``r`` refreshes."""

    BINDINGS = [
        ("k", "cycle_kind", "Kind filter"),
        ("t", "cycle_status", "Status filter"),
        ("y", "synth", "Synth"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._kind_i = 0
        self._status_i = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="pages")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#pages", DataTable)
        table.add_columns("kind", "title", "slug", "status", "updated")
        table.cursor_type = "row"
        self.load()

    def _filters(self) -> tuple[str | None, str | None]:
        return _KIND_CYCLE[self._kind_i], _STATUS_CYCLE[self._status_i]

    def action_cycle_kind(self) -> None:
        self._kind_i = (self._kind_i + 1) % len(_KIND_CYCLE)
        self.load()

    def action_cycle_status(self) -> None:
        self._status_i = (self._status_i + 1) % len(_STATUS_CYCLE)
        self.load()

    def action_refresh(self) -> None:
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        kind, status = self._filters()
        try:
            rows = tui_data.pages(kind=kind, status=status)
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"load failed: {exc}", severity="error")
            return
        self.app.call_from_thread(self._populate, rows, kind, status)

    def _populate(self, rows: list[dict[str, Any]], kind: str | None, status: str | None) -> None:
        table = self.query_one("#pages", DataTable)
        table.clear()
        for r in rows:
            updated = r["updated_at"].strftime("%Y-%m-%d %H:%M") if r["updated_at"] else "-"
            table.add_row(r["kind"], (r["title"] or "")[:40], r["slug"], r["status"], updated)
        table.border_title = f"Pages  kind={kind or 'all'}  status={status or 'all'}"

    def action_synth(self) -> None:
        self.app.push_screen(
            FormModal(
                "Synthesize a page",
                [("kind", "Kind (concept/topic)", "concept"), ("name", "Name", "")],
            ),
            self._on_synth,
        )

    def _on_synth(self, result: dict | None) -> None:
        if result and result.get("name"):
            self._run_synth(result.get("kind") or "concept", result["name"])

    @work(thread=True, exclusive=True)
    def _run_synth(self, kind: str, name: str) -> None:
        try:
            slug = tui_data.synth(kind, name)
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"synth failed: {exc}", severity="error")
            return
        self.app.call_from_thread(self.notify, f"synth: wrote {kind} '{slug}'")
        self.app.call_from_thread(self.load)
