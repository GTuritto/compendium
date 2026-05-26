"""A placeholder screen for operational concerns not yet built.

Keeps every navigation target reachable while screens land sub-phase by
sub-phase; replaced by the real screen as each is implemented.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class PlaceholderScreen(Screen):
    """Shows the screen's name and a 'coming soon' note."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"{self._title} — coming soon", id="placeholder")
        yield Footer()
