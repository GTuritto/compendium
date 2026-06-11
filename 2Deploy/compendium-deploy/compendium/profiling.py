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
- ``mem_arm()`` / ``mem_report()`` do baseline-and-diff allocation tracking
  with stdlib ``tracemalloc`` for leak hunting in long-running processes.
  Arm takes the baseline; report diffs current allocations against it,
  writes ``mem-<timestamp>.txt`` into the profile directory, and returns the
  text. The serve daemon installs SIGUSR1 (arm) / SIGUSR2 (report) handlers
  via ``install_memory_signal_handlers()``; handler failures are swallowed
  so the daemon is never disturbed.

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


# --- memory: tracemalloc baseline-and-diff (leak hunting) -------------------

_MEM_TOP_SITES = 15
_mem_baseline: object | None = None


def mem_arm() -> None:
    """Start tracemalloc (if needed) and take the baseline snapshot.

    Allocation tracking begins here; a later :func:`mem_report` shows growth
    relative to this point. Re-arming replaces the baseline.
    """
    import tracemalloc

    global _mem_baseline
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    _mem_baseline = tracemalloc.take_snapshot()
    log.info("mem_armed")


def mem_report(top: int = _MEM_TOP_SITES) -> str:
    """Diff current allocations against the baseline and write the artifact.

    Returns the report text: top growth sites by line, tracemalloc traced
    size (current and peak), and process RSS (current via ``ps``, peak via
    ``resource``). Writes ``mem-<timestamp>.txt`` into :func:`profile_dir`.
    """
    import tracemalloc

    if _mem_baseline is None or not tracemalloc.is_tracing():
        return "memory profiler not armed; arm first (SIGUSR1 or mem_arm())"

    snapshot = tracemalloc.take_snapshot()
    diffs = snapshot.compare_to(_mem_baseline, "lineno")  # type: ignore[arg-type]
    traced, peak_traced = tracemalloc.get_traced_memory()
    rss_current, rss_peak = _rss_bytes()

    lines = [
        f"memory report — {datetime.now().isoformat(timespec='seconds')}",
        f"traced: {traced / 1048576:.1f} MiB (peak {peak_traced / 1048576:.1f} MiB)",
        "rss: "
        + (f"current {rss_current / 1048576:.1f} MiB, " if rss_current else "")
        + f"peak {rss_peak / 1048576:.1f} MiB",
        f"top {top} allocation growth sites since baseline:",
    ]
    lines += [f"  {d}" for d in diffs[:top]]
    text = "\n".join(lines)

    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = profile_dir() / f"mem-{stamp}.txt"
        out_path.write_text(text + "\n", encoding="utf-8")
        log.info("mem_report_written", path=str(out_path))
    except Exception as exc:  # the report text still goes back to the caller
        log.warning("mem_report_write_failed", error=repr(exc))
    return text


def _rss_bytes() -> tuple[int | None, int]:
    """(current RSS or None, peak RSS) in bytes, stdlib only.

    Peak comes from ``resource.getrusage`` (bytes on macOS, KiB on Linux);
    current comes from ``ps -o rss=`` because macOS has no ``/proc``.
    """
    import resource
    import subprocess

    ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = ru_maxrss if sys.platform == "darwin" else ru_maxrss * 1024
    current: int | None = None
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            capture_output=True, text=True, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            current = int(out.stdout.strip()) * 1024  # ps reports KiB
    except Exception:
        current = None
    return current, peak


def install_memory_signal_handlers() -> bool:
    """Install SIGUSR1 (arm) / SIGUSR2 (report) for a long-running process.

    Must run in the main thread (the serve daemon calls it before uvicorn
    starts). Handler bodies are fenced: a failing arm or report logs a
    warning and never disturbs the host process. Returns whether the
    handlers were installed.
    """
    import signal

    def _arm(signum: int, frame: object) -> None:
        try:
            mem_arm()
        except Exception as exc:
            log.warning("mem_arm_failed", error=repr(exc))

    def _report(signum: int, frame: object) -> None:
        try:
            mem_report()
        except Exception as exc:
            log.warning("mem_report_failed", error=repr(exc))

    try:
        signal.signal(signal.SIGUSR1, _arm)
        signal.signal(signal.SIGUSR2, _report)
    except (AttributeError, ValueError, OSError) as exc:
        # No SIGUSR* on this platform, or not the main thread.
        log.warning("mem_signals_unavailable", error=repr(exc))
        return False
    log.info("mem_signals_installed", arm="SIGUSR1", report="SIGUSR2")
    return True
