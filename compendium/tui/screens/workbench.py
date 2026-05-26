"""Query workbench screen (Phase 8d).

Type a query, run the Phase 5 pipeline (which persists a trace), and inspect the
result: the fused ranking, coverage, fallback, and any gaps. The run is a real,
traced query, so it also shows up on the dashboard's recent traces.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static


class WorkbenchScreen(Screen):
    """A query box over the live retrieval pipeline."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Type a query and press Enter", id="q")
        yield Static("", id="summary")
        yield DataTable(id="results")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results", DataTable)
        table.add_columns("rank", "title", "kind", "score")
        self.query_one("#q", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.query_one("#summary", Static).update("running…")
            self.run_query(text)

    @work(thread=True, exclusive=True)
    def run_query(self, text: str) -> None:
        from compendium.tui import data as tui_data

        try:
            result = tui_data.run_query(text)
        except Exception as exc:
            self.app.call_from_thread(
                self.query_one("#summary", Static).update, f"[error] {exc}"
            )
            return
        self.app.call_from_thread(self._populate, result)

    def _populate(self, result: Any) -> None:
        fb = ", chunk fallback" if result.fallback_to_chunks else ""
        gaps = f", {len(result.gaps)} gap(s)" if result.gaps else ""
        self.query_one("#summary", Static).update(
            f"{len(result.pages)} page(s)  coverage {result.coverage_score:.3f}{fb}{gaps}"
        )
        table = self.query_one("#results", DataTable)
        table.clear()
        for i, p in enumerate(result.pages, start=1):
            table.add_row(str(i), p.title[:45], p.kind, f"{p.score:.5f}")
        for c in result.citations:
            table.add_row("·", f"chunk: {(c.source_title or c.entity_id)[:40]}", "chunk", f"{c.score:.5f}")
