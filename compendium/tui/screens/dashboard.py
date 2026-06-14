"""Dashboard screen: counts, sync lag, and recent traces (Phase 8a)."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual import work
from textual.widgets import DataTable, Footer, Header, Static

from compendium.cli import render
from compendium.tui import data as tui_data
from compendium.tui.screens.base import DataScreen


class DashboardScreen(DataScreen):
    """Point-in-time operational state, refreshable with ``r``."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("R", "reindex", "Reindex"),
        ("G", "graph_rebuild", "Rebuild graph"),
        ("I", "process_inbox", "Process inbox"),
    ]

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

    # --- admin ops (ADR-020): non-destructive, call the shared CLI seam ------

    def action_reindex(self) -> None:
        self._admin(
            tui_data.reindex_all, "reindex",
            lambda r: f"reindexed {r.indexed}, failed {r.failed}",
        )

    def action_graph_rebuild(self) -> None:
        self._admin(tui_data.graph_rebuild, "graph rebuild", lambda r: "graph rebuilt")

    def action_process_inbox(self) -> None:
        self._admin(
            tui_data.process_inbox, "inbox process",
            lambda r: f"processed {getattr(r, 'processed', 0)}, "
            f"failed {getattr(r, 'failed', 0)}",
        )

    @work(thread=True, exclusive=False)
    def _admin(self, fn: Any, label: str, summary: Any) -> None:
        self.run_threaded(
            fn,
            on_ok=lambda r: self._admin_done(label, summary(r)),
            on_error=lambda exc: self.notify(
                f"{label} failed: {exc}", severity="error"
            ),
        )

    def _admin_done(self, label: str, message: str) -> None:
        self.notify(f"{label}: {message}")
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        self.run_threaded(
            tui_data.dashboard,
            on_ok=self._populate,
            on_error=lambda exc: self._error(str(exc)),
        )

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
            traces.add_row(
                render.fmt_coverage(t["coverage_score"]),
                render.fmt_fallback(t["fallback_to_chunks"]),
                t["query_text"][:40],
            )

    def _error(self, message: str) -> None:
        self.query_one("#counts", Static).update(f"[error] {message}")
