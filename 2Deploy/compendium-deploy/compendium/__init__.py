"""Compendium: a personal knowledge synthesis system."""

from pathlib import Path


def _read_version() -> str:
    """Read the canonical version from the root ``VERSION`` file.

    ``VERSION`` is the single source of truth (see ``CHANGELOG.md`` and the v0.3
    build plan). It sits at the repo / bundle root, one level above this package,
    so the package is run in place (``pythonpath = ["."]``) without an install
    step. Falls back to a sentinel if the file is absent (e.g. a stripped build).
    """
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0+unknown"


__version__ = _read_version()
