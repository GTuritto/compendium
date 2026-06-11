"""Local, opt-in profiling: timed spans via structlog, cProfile via the CLI.

Two layers, both local-first (no new stores, no new dependencies):

- ``timed(stage, ...)`` wraps a block and measures wall-clock milliseconds.
  When a ``sink`` dict is given the duration is always recorded into it (the
  retrieval pipeline feeds its existing ``latencies_ms`` trace field this
  way). A ``profile`` structlog event is emitted only when profiling is
  enabled, so the hot paths stay silent by default.
- ``cpu_profile(command)`` wraps a block in stdlib ``cProfile``, writes a
  ``.prof`` artifact into the local profile directory for ``pstats`` /
  snakeviz, and prints a top-25 cumulative summary to stderr. The CLI's
  global ``--profile`` flag uses it. A profiling failure never breaks the
  profiled operation: every profiler step is fenced and logged on error.

Artifacts land in ``~/.compendium/profiles`` (override with
``COMPENDIUM_PROFILE_DIR``). Profiling is enabled by ``COMPENDIUM_PROFILE``
in the environment; the empty string and ``0`` / ``false`` / ``no`` / ``off``
(any case) count as off.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from compendium.logging import get_logger

_FALSY = {"", "0", "false", "no", "off"}
_SUMMARY_LINES = 25

log = get_logger(__name__)


def profile_dir() -> Path:
    """The local directory all profiler artifacts are written to.

    ``COMPENDIUM_PROFILE_DIR`` overrides the default ``~/.compendium/profiles``.
    Created on first use.
    """
    override = os.environ.get("COMPENDIUM_PROFILE_DIR", "").strip()
    base = Path(override).expanduser() if override else Path.home() / ".compendium" / "profiles"
    base.mkdir(parents=True, exist_ok=True)
    return base


def enabled() -> bool:
    """True when COMPENDIUM_PROFILE is set to a truthy value."""
    return os.environ.get("COMPENDIUM_PROFILE", "").strip().lower() not in _FALSY


@contextmanager
def timed(
    stage: str,
    *,
    sink: dict[str, float] | None = None,
    **fields: object,
) -> Iterator[None]:
    """Time a block. Always fills ``sink[stage]`` (ms) when a sink is given;
    emits a ``profile`` log event only when profiling is enabled.

    The duration is recorded even when the block raises, so a failing stage
    still shows up in the span log and the sink.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        if sink is not None:
            sink[stage] = duration_ms
        if enabled():
            log.info("profile", stage=stage, duration_ms=round(duration_ms, 3), **fields)


@contextmanager
def cpu_profile(command: str) -> Iterator[None]:
    """Run the block under cProfile; the block's outcome is never affected.

    Writes ``<command>-<timestamp>.prof`` into :func:`profile_dir` and prints
    the artifact path plus a top-25 cumulative summary to stderr. Inspect the
    artifact with ``python -m pstats <path>`` or snakeviz. Every profiler step
    (enable, dump, summary) is fenced: on failure it logs a warning and the
    profiled operation, including any exception it raises, passes through
    untouched.
    """
    import cProfile

    profiler: cProfile.Profile | None = None
    try:
        profiler = cProfile.Profile()
        profiler.enable()
    except Exception as exc:
        log.warning("cpu_profile_failed", step="enable", error=repr(exc))
        profiler = None
    try:
        yield
    finally:
        if profiler is not None:
            try:
                profiler.disable()
                _write_cpu_profile(profiler, command)
            except Exception as exc:
                log.warning("cpu_profile_failed", step="report", error=repr(exc))


def _write_cpu_profile(profiler: object, command: str) -> None:
    """Dump the ``.prof`` artifact and print the top-25 cumulative summary."""
    import pstats

    slug = "-".join(command.split()) or "compendium"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = profile_dir() / f"{slug}-{stamp}.prof"
    profiler.dump_stats(str(out_path))  # type: ignore[attr-defined]
    log.info("profile_written", path=str(out_path))
    print(f"\ncpu profile written: {out_path}", file=sys.stderr)
    stats = pstats.Stats(profiler, stream=sys.stderr)  # type: ignore[arg-type]
    stats.sort_stats("cumulative").print_stats(_SUMMARY_LINES)
