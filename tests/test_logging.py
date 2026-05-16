"""Tests for structured logging."""

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_log_output_is_json_on_stderr():
    # Run in a subprocess so the structlog stderr stream is captured cleanly.
    code = (
        "from compendium.logging import get_logger; "
        "get_logger('test').info('hello', foo='bar')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    line = result.stderr.strip()
    event = json.loads(line)  # single-line JSON, or this raises
    assert event["event"] == "hello"
    assert event["level"] == "info"
    assert "ts" in event
    assert event["foo"] == "bar"
