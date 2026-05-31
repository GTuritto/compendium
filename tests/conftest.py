"""Shared pytest configuration.

Currently the only thing here is the ``--golden-baseline`` CLI flag
that switches the golden runner from "compare to baseline.json" to
"regenerate baseline.json from the live run". Added in v0.2 Phase 5.
"""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--golden-baseline",
        action="store_true",
        default=False,
        help=(
            "Regenerate tests/golden/baseline.json from the live golden run "
            "instead of asserting against it (v0.2 Phase 5)."
        ),
    )
