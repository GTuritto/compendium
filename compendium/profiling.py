"""Local, opt-in profiling: timed spans via structlog, cProfile via the CLI.

Two layers, both local-first (no new stores, no new dependencies):

- ``timed(stage, ...)`` wraps a block and measures wall-clock milliseconds.
  When a ``sink`` dict is given the duration is always recorded into it (the
  retrieval pipeline feeds its existing ``latencies_ms`` trace field this
  way). A ``profile`` structlog event is emitted only when profiling is
  enabled, so the hot paths stay silent by default.
- ``cpu_profile(out_path)`` wraps a block in stdlib ``cProfile`` and dumps a
  ``.prof`` file for ``pstats`` / snakeviz. The CLI's global ``--profile``
  flag uses it.

Profiling is enabled by ``COMPENDIUM_PROFILE`` in the environment; the empty
string and ``0`` / ``false`` / ``no`` / ``off`` (any case) count as off.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from compendium.logging import get_logger

_FALSY = {"", "0", "false", "no", "off"}

log = get_logger(__name__)


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
def cpu_profile(out_path: str) -> Iterator[None]:
    """Run the block under cProfile and dump stats to ``out_path``.

    Inspect with ``python -m pstats <out_path>`` or snakeviz.
    """
    import cProfile

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        yield
    finally:
        profiler.disable()
        profiler.dump_stats(out_path)
        log.info("profile_written", path=out_path)
