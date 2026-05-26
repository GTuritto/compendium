"""Graph browser screen (Phase 8e).

Search Memgraph nodes by title/slug, then walk typed edges N hops from the
selected node. Read-only; reports an unreachable graph rather than crashing.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static


class GraphScreen(Screen):
    """Node search (top) and an N-hop edge walk of the selection (bottom).

    Press ``/`` to focus the search box; after a search, focus moves to the node
    list so the navigation keys are not swallowed by the input. Select a node row
    (Enter) to walk its edges.
    """

    BINDINGS = [("slash", "focus_search", "Search")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search nodes by title/slug, Enter to search", id="q")
        yield Static("", id="status")
        with Horizontal():
            yield DataTable(id="nodes")
            yield DataTable(id="edges")
        yield Footer()

    def on_mount(self) -> None:
        nodes = self.query_one("#nodes", DataTable)
        nodes.add_columns("kind", "label", "id")
        nodes.cursor_type = "row"
        nodes.border_title = "Nodes (Enter to walk)"
        edges = self.query_one("#edges", DataTable)
        edges.add_columns("from", "type", "to")
        edges.border_title = "Edges"
        nodes.focus()  # nav keys work; '/' focuses the search box

    def action_focus_search(self) -> None:
        self.query_one("#q", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        term = event.value.strip()
        if term:
            self.query_one("#status", Static).update("searching…")
            self.search(term)

    @work(thread=True, exclusive=True)
    def search(self, term: str) -> None:
        from compendium.tui import data as tui_data

        try:
            nodes = tui_data.graph_search(term)
        except tui_data.GraphUnreachable:
            self.app.call_from_thread(
                self.query_one("#status", Static).update, "[memgraph unreachable]"
            )
            return
        self.app.call_from_thread(self._show_nodes, nodes)

    def _show_nodes(self, nodes: list[dict[str, Any]]) -> None:
        table = self.query_one("#nodes", DataTable)
        table.clear()
        self._node_ids: list[str] = []
        for n in nodes:
            table.add_row(n["kind"], n["label"][:40], n["id"])
            self._node_ids.append(n["id"])
        self.query_one("#status", Static).update(
            f"{len(nodes)} node(s) — select one and press Enter to walk"
        )
        if nodes:
            table.focus()  # so Enter walks the selection rather than re-searching

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        ids = getattr(self, "_node_ids", [])
        row = event.cursor_row
        if 0 <= row < len(ids):
            self.walk(ids[row])

    @work(thread=True, exclusive=True)
    def walk(self, node_id: str) -> None:
        from compendium.tui import data as tui_data

        try:
            graph = tui_data.graph_walk(node_id, hops=2)
        except tui_data.GraphUnreachable:
            self.app.call_from_thread(
                self.query_one("#status", Static).update, "[memgraph unreachable]"
            )
            return
        self.app.call_from_thread(self._show_edges, graph)

    def _show_edges(self, graph: dict[str, Any]) -> None:
        table = self.query_one("#edges", DataTable)
        table.clear()
        for e in graph["edges"]:
            table.add_row(e["from"][:20], e["type"], e["to"][:20])
        self.query_one("#status", Static).update(
            f"{len(graph['nodes'])} node(s), {len(graph['edges'])} edge(s) within 2 hops"
        )
