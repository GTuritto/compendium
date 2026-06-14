"""The Compendium ops console (ADR-008): a keyboard-driven Textual app.

One screen per operational concern, reached by a mnemonic key shown in the
footer.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from compendium.tui.screens.curation import CurationScreen
from compendium.tui.screens.dashboard import DashboardScreen
from compendium.tui.screens.graph import GraphScreen
from compendium.tui.screens.pages import PagesScreen
from compendium.tui.screens.sources import SourcesScreen
from compendium.tui.screens.workbench import WorkbenchScreen

# Navigation order: (key, screen name, label).
_NAV = [
    ("d", "dashboard", "Dashboard"),
    ("s", "sources", "Sources"),
    ("p", "pages", "Pages"),
    ("w", "workbench", "Workbench"),
    ("c", "curation", "Curation"),
    ("g", "graph", "Graph"),
]


class HelpScreen(ModalScreen):
    """A modal listing the navigation and global bindings."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        lines = ["Compendium ops console — bindings", ""]
        lines += [f"  {key}    {label}" for key, _, label in _NAV]
        lines += ["", "  ?    Help", "  q    Quit", "", "(esc to close)"]
        yield Static("\n".join(lines), id="help")


def _screen_for(name: str):
    """Build the screen registered for a navigation target."""
    builders = {
        "dashboard": DashboardScreen,
        "sources": SourcesScreen,
        "pages": PagesScreen,
        "workbench": WorkbenchScreen,
        "curation": CurationScreen,
        "graph": GraphScreen,
    }
    return builders[name]()


class CompendiumTUI(App):
    """The ops console app."""

    TITLE = "Compendium"
    BINDINGS = [
        *[Binding(key, f"nav('{name}')", label) for key, name, label in _NAV],
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(_screen_for("dashboard"))

    def action_nav(self, name: str) -> None:
        # Replace the current base screen; dismiss a modal first if open.
        if isinstance(self.screen, (HelpScreen, ModalScreen)):
            self.pop_screen()
        self.switch_screen(_screen_for(name))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())


def run() -> int:
    """Launch the ops console (``compendium tui``)."""
    CompendiumTUI().run()
    return 0
