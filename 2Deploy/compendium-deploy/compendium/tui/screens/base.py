"""Shared Screen base for the ops console (review #2, candidate 4).

Every screen runs its blocking data calls on a worker thread and marshals the
result back to the UI thread. ``run_threaded`` centralizes that cycle — the
try/except plus the two ``call_from_thread`` hops — so a worker method is just
its ``@work(thread=True)`` declaration plus one call.
"""

from __future__ import annotations

from typing import Any, Callable

from textual.screen import Screen


class DataScreen(Screen):
    """A Screen that threads blocking data calls and marshals results to the UI."""

    def run_threaded(
        self,
        fn: Callable[[], Any],
        *,
        on_ok: Callable[[Any], None],
        on_error: Callable[[Exception], None] | None = None,
        error_label: str = "operation",
    ) -> None:
        """Run ``fn`` on the current worker thread, then marshal back to the UI.

        On success calls ``on_ok(result)``; on any exception calls ``on_error(exc)``
        if given, otherwise notifies ``"{error_label} failed: …"`` at error
        severity. Both callbacks run on the UI thread. Call only from inside a
        ``@work(thread=True)`` method.
        """
        try:
            result = fn()
        except Exception as exc:
            if on_error is not None:
                self.app.call_from_thread(on_error, exc)
            else:
                self.app.call_from_thread(self._io_error, error_label, exc)
            return
        self.app.call_from_thread(on_ok, result)

    def _io_error(self, error_label: str, exc: Exception) -> None:
        self.notify(f"{error_label} failed: {exc}", severity="error")
