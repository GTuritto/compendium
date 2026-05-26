"""Dashboard screen: counts, sync lag, and recent traces (Phase 8a)."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual import work
from textual.widgets import DataTable, Footer, Header, Static

from compendium.tui import data as tui_data


class DashboardScreen(Screen):
    """Point-in-time operational state, refreshable with ``r``."""

    BINDINGS = [("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Counts", classes="section")
        yield Static(id="counts")
        with Horizontal():
            yield DataTable(id="sync_lag")
            yield DataTable(id="recent_traces")
        yield Footer()

    def on_mount(self) -> None:
        lag = self.query_one("#sync_lag", DataTable)
        lag.add_columns("index_kind", "state", "n")
        lag.border_title = "Sync lag"
        traces = self.query_one("#recent_traces", DataTable)
        traces.add_columns("coverage", "fallback", "query")
        traces.border_title = "Recent traces"
        self.load()

    def action_refresh(self) -> None:
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        try:
            payload = tui_data.dashboard()
        except Exception as exc:  # DB down or query failed
            self.app.call_from_thread(self._error, str(exc))
            return
        self.app.call_from_thread(self._populate, payload)

    def _populate(self, payload: dict[str, Any]) -> None:
        counts = payload["counts"]
        self.query_one("#counts", Static).update(
            "  ".join(f"{k}={v}" for k, v in counts.items())
        )
        lag = self.query_one("#sync_lag", DataTable)
        lag.clear()
        for row in payload["sync_lag"]:
            lag.add_row(row["index_kind"], row["state"], str(row["n"]))
        traces = self.query_one("#recent_traces", DataTable)
        traces.clear()
        for t in payload["recent_traces"]:
            cov = f"{t['coverage_score']:.3f}" if t["coverage_score"] is not None else "-"
            fb = "fallback" if t["fallback_to_chunks"] else "ok"
            traces.add_row(cov, fb, t["query_text"][:40])

    def _error(self, message: str) -> None:
        self.query_one("#counts", Static).update(f"[error] {message}")
