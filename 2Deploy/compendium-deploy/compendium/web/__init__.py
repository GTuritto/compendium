"""The web UI launcher (ADR-015, v0.3 Phase 2).

``compendium web`` runs the packaged Streamlit app as a separate colocated
process, **loopback-only by default** — the bind address is centralized here,
exactly like ``serve``'s. Manual launch only in v0.3 (no service unit; it is
an interactive surface, not a background daemon). Network exposure is the
shared v0.4 decision with ADR-011 (auth + TLS), not a flag to flip.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8501


def streamlit_argv(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> list[str]:
    """The exact Streamlit invocation ``compendium web`` runs."""
    app = Path(__file__).resolve().parent / "app.py"
    return [
        sys.executable, "-m", "streamlit", "run", str(app),
        "--server.address", host,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]


def run(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """Launch the web UI; returns Streamlit's exit code."""
    return subprocess.run(streamlit_argv(host, port)).returncode
