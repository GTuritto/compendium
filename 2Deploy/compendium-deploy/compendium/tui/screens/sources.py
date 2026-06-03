"""Source list screen with an ingest action (Phase 8b)."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.widgets import DataTable, Footer, Header

from compendium.cli import render
from compendium.tui import data as tui_data
from compendium.tui.screens.base import DataScreen
from compendium.tui.screens.widgets import FormModal

_SOURCE_KINDS = "book, article, paper, note, web"


class SourcesScreen(DataScreen):
    """Sources with inspection status; ``i`` ingests, ``r`` refreshes."""

    BINDINGS = [("i", "ingest", "Ingest"), ("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="sources")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#sources", DataTable)
        table.add_columns("kind", "title", "inspection", "ingested")
        table.cursor_type = "row"
        self.load()

    def action_refresh(self) -> None:
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        self.run_threaded(tui_data.sources, on_ok=self._populate, error_label="load")

    def _populate(self, rows: list[dict[str, Any]]) -> None:
        table = self.query_one("#sources", DataTable)
        table.clear()
        for r in rows:
            table.add_row(
                r["kind"], (r["title"] or "")[:50], r["inspection_status"] or "-",
                render.fmt_ts(r["ingested_at"]),
            )

    def action_ingest(self) -> None:
        self.app.push_screen(
            FormModal(
                f"Ingest a source (kinds: {_SOURCE_KINDS})",
                [("path", "Path or URL", ""), ("kind", "Kind", "article")],
            ),
            self._on_ingest,
        )

    def _on_ingest(self, result: dict | None) -> None:
        if result and result.get("path"):
            self._run_ingest(result["path"], result.get("kind") or "article")

    @work(thread=True, exclusive=True)
    def _run_ingest(self, path: str, kind: str) -> None:
        def done(results: list[Any]) -> None:
            stored = sum(1 for r in results if r.status in ("ingested", "updated"))
            self.notify(f"ingest: {stored} stored, {len(results)} source(s)")
            self.load()

        self.run_threaded(
            lambda: tui_data.ingest_path(path, kind=kind),
            on_ok=done, error_label="ingest",
        )
