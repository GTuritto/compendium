"""Application entrypoint: ``python -m compendium [ingest <path>]``.

With no subcommand, loads and validates configuration, reports startup, and
exits. The ``ingest`` subcommand runs the ingestion pipeline.
"""

from __future__ import annotations

import argparse
import sys

from compendium.config import ConfigError, load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.ingest.pipeline import ingest
from compendium.logging import get_logger
from compendium.wiki.lint import errors_only, lint_vault, load_vault_pages
from compendium.wiki.source_page import generate_source_page

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


def _lint() -> int:
    log = get_logger("compendium.lint")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    pages, issues = load_vault_pages(config.vault_path)
    source_ids: set[str] | None = None
    try:
        with connection() as conn:
            source_ids = {
                str(row["id"]) for row in conn.execute("SELECT id FROM sources")
            }
    except Exception as exc:  # lint still runs, minus source-id-resolves
        log.warning("lint: source-id-resolves skipped", error=str(exc))

    issues = issues + lint_vault(pages, known_source_ids=source_ids)
    errors = errors_only(issues)
    for issue in issues:
        print(
            f"  {issue.severity}: [{issue.page}] {issue.rule}: {issue.message}",
            file=sys.stderr,
        )
    print(
        f"lint: {len(pages)} page(s), {len(errors)} error(s), "
        f"{len(issues) - len(errors)} warning(s)",
        file=sys.stderr,
    )
    return 1 if errors else 0


def _pages_build() -> int:
    log = get_logger("compendium.pages")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    built = 0
    with connection() as conn:
        for source_id in repository.sources_without_page(conn):
            page = generate_source_page(
                conn, source_id, vault_path=config.vault_path
            )
            if page is not None:
                built += 1
                log.info("source page built", slug=page.slug)
    print(f"pages build: {built} source page(s) generated", file=sys.stderr)
    return 0


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

    subparsers.add_parser("lint", help="lint the wiki vault")

    pages_parser = subparsers.add_parser("pages", help="wiki page operations")
    pages_parser.add_argument(
        "action", choices=["build"], help="build: backfill missing source pages"
    )

    args = parser.parse_args(argv)

    if args.command == "ingest":
        return _ingest(args.path, args.kind, args.mine)
    if args.command == "lint":
        return _lint()
    if args.command == "pages":
        return _pages_build()
    return _startup()


if __name__ == "__main__":
    sys.exit(main())
