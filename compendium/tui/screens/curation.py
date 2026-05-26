"""Curation queue screen (Phase 8e): a read-only view of open signals.

Renders ``v_open_curation_signals`` by priority. The queue is empty until Phase
9's slow loop writes signals; the curator actions (trigger synth from a signal,
mark addressed) land in Phase 9.
"""

from __future__ import annotations

import json
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


class CurationScreen(Screen):
    """Open curation signals, highest priority first; read-only in v0.1."""

    BINDINGS = [("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        yield DataTable(id="signals")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#signals", DataTable)
        table.add_columns("priority", "kind", "summary", "created")
        self.load()

    def action_refresh(self) -> None:
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        from compendium.tui import data as tui_data

        try:
            rows = tui_data.curation_signals()
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"load failed: {exc}", severity="error")
            return
        self.app.call_from_thread(self._populate, rows)

    def _populate(self, rows: list[dict[str, Any]]) -> None:
        table = self.query_one("#signals", DataTable)
        table.clear()
        for r in rows:
            created = r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "-"
            summary = json.dumps(r["payload"])[:50] if r["payload"] else ""
            table.add_row(str(r["priority"]), r["kind"], summary, created)
        note = "no open signals (Phase 9 feeds this queue)" if not rows else f"{len(rows)} open signal(s)"
        self.query_one("#status", Static).update(note)
