"""Curation queue screen (Phase 8e): a read-only view of open signals.

Renders ``v_open_curation_signals`` by priority. The queue is empty until Phase
9's slow loop writes signals; the curator actions (trigger synth from a signal,
mark addressed) land in Phase 9.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from compendium.cli import render


class CurationScreen(Screen):
    """Open curation signals, highest priority first.

    Select a signal and press ``y`` to synthesize a draft from it (Phase 9); the
    signal moves to ``in_progress`` and leaves the open queue.
    """

    BINDINGS = [("r", "refresh", "Refresh"), ("y", "synth", "Synth from signal")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        yield DataTable(id="signals")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#signals", DataTable)
        table.add_columns("priority", "kind", "summary", "created")
        table.cursor_type = "row"
        self._signal_ids: list[str] = []
        table.focus()  # so the cursor is on a row and 'y' acts on the selection
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
        self._signal_ids = []
        for r in rows:
            summary = render.fmt_payload(r["payload"], 50)
            table.add_row(
                str(r["priority"]), r["kind"], summary, render.fmt_ts(r["created_at"])
            )
            self._signal_ids.append(str(r["id"]))
        note = "no open signals" if not rows else f"{len(rows)} open signal(s) — y to synth"
        self.query_one("#status", Static).update(note)

    def action_synth(self) -> None:
        table = self.query_one("#signals", DataTable)
        row = table.cursor_row
        if row is None or row >= len(self._signal_ids):
            return
        self._synth(self._signal_ids[row])

    @work(thread=True, exclusive=True)
    def _synth(self, signal_id: str) -> None:
        from compendium.tui import data as tui_data

        try:
            slug = tui_data.synth_signal(signal_id)
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"synth failed: {exc}", severity="error")
            return
        self.app.call_from_thread(self.notify, f"synth: drafted '{slug}'")
        self.app.call_from_thread(self.load)
