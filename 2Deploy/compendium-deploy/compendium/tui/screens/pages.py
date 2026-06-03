"""Page list screen with filters and a synth action (Phase 8c)."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.widgets import DataTable, Footer, Header

from compendium.cli import render
from compendium.tui import data as tui_data
from compendium.tui.screens.base import DataScreen
from compendium.tui.screens.widgets import FormModal

_KIND_CYCLE = [None, "source", "concept", "topic"]
_STATUS_CYCLE = [None, "draft", "canonical", "deprecated"]


class PagesScreen(DataScreen):
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
        self.run_threaded(
            lambda: tui_data.pages(kind=kind, status=status),
            on_ok=lambda rows: self._populate(rows, kind, status),
            error_label="load",
        )

    def _populate(self, rows: list[dict[str, Any]], kind: str | None, status: str | None) -> None:
        table = self.query_one("#pages", DataTable)
        table.clear()
        for r in rows:
            table.add_row(
                r["kind"], (r["title"] or "")[:40], r["slug"], r["status"],
                render.fmt_ts(r["updated_at"]),
            )
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
        def done(slug: str) -> None:
            self.notify(f"synth: wrote {kind} '{slug}'")
            self.load()

        self.run_threaded(
            lambda: tui_data.synth(kind, name), on_ok=done, error_label="synth"
        )
