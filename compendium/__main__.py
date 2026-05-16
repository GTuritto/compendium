"""Application entrypoint: ``python -m compendium``.

Loads and validates configuration, reports startup with the resolved
storage URLs, and exits cleanly. No storage backend is contacted.
"""

from __future__ import annotations

import sys

from compendium.config import ConfigError, load_config
from compendium.logging import get_logger


def main() -> int:
    log = get_logger("compendium")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    log.info("Compendium starting", **config.storage_urls())
    return 0


if __name__ == "__main__":
    sys.exit(main())
