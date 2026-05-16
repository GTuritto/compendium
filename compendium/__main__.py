"""Application entrypoint: ``python -m compendium [ingest <path>]``.

With no subcommand, loads and validates configuration, reports startup, and
exits. The ``ingest`` subcommand runs the ingestion pipeline.
"""

from __future__ import annotations

import argparse
import sys

from compendium.config import ConfigError, load_config
from compendium.ingest.pipeline import ingest
from compendium.logging import get_logger

_SOURCE_KINDS = ["book", "article", "paper", "note", "web"]


def _startup() -> int:
    log = get_logger("compendium")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    log.info("Compendium starting", **config.storage_urls())
    return 0


def _ingest(path: str, kind: str, mine: bool) -> int:
    log = get_logger("compendium.ingest")
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    results = ingest(path, kind=kind, mine=mine)
    for result in results:
        log.info(
            "ingested",
            path=result.path,
            status=result.status,
            chunks=result.chunk_count,
            detail=result.detail,
        )
    stored = sum(1 for r in results if r.status in ("ingested", "updated"))
    unchanged = sum(1 for r in results if r.status == "unchanged")
    failed = sum(1 for r in results if r.status == "failed")
    print(
        f"{len(results)} source(s): {stored} stored, "
        f"{unchanged} unchanged, {failed} failed",
        file=sys.stderr,
    )
    return 1 if failed and failed == len(results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compendium")
    subparsers = parser.add_subparsers(dest="command")
    ingest_parser = subparsers.add_parser(
        "ingest", help="ingest a file, URL, or directory"
    )
    ingest_parser.add_argument("path", help="file path, URL, or directory")
    ingest_parser.add_argument(
        "--kind", default="article", choices=_SOURCE_KINDS, help="source kind"
    )
    ingest_parser.add_argument(
        "--mine", action="store_true", help="mark the source as authored by you"
    )
    args = parser.parse_args(argv)

    if args.command == "ingest":
        return _ingest(args.path, args.kind, args.mine)
    return _startup()


if __name__ == "__main__":
    sys.exit(main())
