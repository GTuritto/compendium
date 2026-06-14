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

    BINDINGS = [
        ("i", "ingest", "Ingest"),
        ("D", "delete", "Delete"),
        ("r", "refresh", "Refresh"),
    ]

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
        self._rows = rows
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

    # --- delete (ADR-018/020): destructive, TUI-only, behind a typed confirm ---

    def action_delete(self) -> None:
        rows = getattr(self, "_rows", [])
        idx = self.query_one("#sources", DataTable).cursor_row
        if idx is None or idx < 0 or idx >= len(rows):
            self.notify("no source selected", severity="warning")
            return
        self._pending_delete = rows[idx]
        title = (rows[idx].get("title") or "")[:40]
        self.app.push_screen(
            FormModal(
                f"DELETE '{title}' and all its data? Type DELETE to confirm.",
                [("confirm", "Confirm", "")],
            ),
            self._on_delete,
        )

    def _on_delete(self, result: dict | None) -> None:
        src = getattr(self, "_pending_delete", None)
        if not result or result.get("confirm") != "DELETE" or src is None:
            self.notify("delete cancelled")
            return
        self._run_delete(str(src["id"]), (src.get("title") or "")[:40])

    @work(thread=True, exclusive=True)
    def _run_delete(self, ident: str, title: str) -> None:
        def done(report: Any) -> None:
            self.notify(f"deleted '{title}': {report.chunk_count} chunk(s)")
            self.load()

        self.run_threaded(
            lambda: tui_data.delete_source(ident), on_ok=done, error_label="delete"
        )
