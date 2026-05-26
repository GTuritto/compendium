"""Shared TUI widgets: a small keyboard form modal for write actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


class FormModal(ModalScreen[dict | None]):
    """A modal collecting one or more text fields.

    ``fields`` is a list of ``(key, label, default)``. Enter submits and
    dismisses with ``{key: value}``; Escape cancels and dismisses with ``None``.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str, fields: list[tuple[str, str, str]]) -> None:
        super().__init__()
        self._title = title
        self._fields = fields

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            yield Static(self._title, id="form_title")
            for key, label, default in self._fields:
                yield Label(label)
                yield Input(value=default, id=f"f_{key}")

    def on_mount(self) -> None:
        first = self._fields[0][0]
        self.query_one(f"#f_{first}", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        self.dismiss(
            {key: self.query_one(f"#f_{key}", Input).value for key, _, _ in self._fields}
        )
