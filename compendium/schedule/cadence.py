"""Interval parsing for ``--every``.

Accepts human-readable strings of the form ``Nh``, ``Nm``, or ``NhMm``;
returns total seconds. Minimum granularity is 60 seconds; maximum is
seven days. Malformed input raises :class:`ScheduleError`.
"""

from __future__ import annotations

import re

_MIN_SECONDS = 60
_MAX_SECONDS = 7 * 24 * 3600  # 7 days

# Match Nh, Nm, or NhMm (digits + h, digits + m, or digits + h + digits + m).
_INTERVAL_PATTERN = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?$")


class ScheduleError(Exception):
    """A scheduler step failed or was rejected by a guard."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


def parse_interval(value: str) -> int:
    """Parse an interval string to total seconds.

    Raises:
        ScheduleError: when the input is empty, malformed, below the
            one-minute minimum, or above the seven-day maximum.
    """
    if not isinstance(value, str) or not value.strip():
        raise ScheduleError(step="parse", detail="cadence is required")
    text = value.strip().lower()
    match = _INTERVAL_PATTERN.fullmatch(text)
    if match is None:
        raise ScheduleError(
            step="parse",
            detail=f"expected Nh, Nm, or NhMm (got '{value}')",
        )
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    if hours == 0 and minutes == 0:
        raise ScheduleError(
            step="parse",
            detail=f"interval must be positive (got '{value}')",
        )
    seconds = hours * 3600 + minutes * 60
    if seconds < _MIN_SECONDS:
        raise ScheduleError(
            step="parse",
            detail=f"interval below 1-minute minimum: {seconds}s",
        )
    if seconds > _MAX_SECONDS:
        raise ScheduleError(
            step="parse",
            detail=f"interval above 7-day maximum: {seconds}s",
        )
    return seconds
