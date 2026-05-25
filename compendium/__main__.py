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
from compendium.wiki.synth import SynthesisError, synthesize_concept, synthesize_topic

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


def _synth(kind: str, name: str, aliases: list[str]) -> int:
    log = get_logger("compendium.synth")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        with connection() as conn:
            if kind == "concept":
                page = synthesize_concept(
                    conn, name, aliases=aliases, vault_path=config.vault_path
                )
            else:
                page = synthesize_topic(
                    conn, name, vault_path=config.vault_path
                )
    except SynthesisError as exc:
        print(f"Synthesis error: {exc}", file=sys.stderr)
        return 1

    log.info("synthesized", kind=kind, slug=page.slug)
    print(f"synth: wrote {kind} page '{page.slug}'", file=sys.stderr)
    return 0


def _reindex(target: str) -> int:
    log = get_logger("compendium.reindex")
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    from compendium.index.sync import reindex

    report = reindex(target)
    log.info(
        "reindex",
        target=target,
        indexed=report.indexed,
        failed=report.failed,
        skipped=report.skipped,
    )
    for error in report.errors:
        print(f"  failed: {error}", file=sys.stderr)
    print(
        f"reindex {target}: {report.indexed} indexed, "
        f"{report.failed} failed, {report.skipped} skipped",
        file=sys.stderr,
    )
    return 1 if report.failed else 0


def _index_sync() -> int:
    log = get_logger("compendium.index")
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    from compendium.index.sync import sync_pending

    report = sync_pending()
    log.info(
        "index sync",
        indexed=report.indexed,
        failed=report.failed,
        skipped=report.skipped,
    )
    for error in report.errors:
        print(f"  failed: {error}", file=sys.stderr)
    print(
        f"index sync: {report.indexed} indexed, "
        f"{report.failed} failed, {report.skipped} skipped",
        file=sys.stderr,
    )
    return 1 if report.failed else 0


def _index_status() -> int:
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    from compendium.index import opensearch, qdrant
    from compendium.index.clients import (
        opensearch_client,
        opensearch_reachable,
        qdrant_client,
        qdrant_reachable,
    )

    os_client = opensearch_client()
    if opensearch_reachable(os_client):
        for index in (opensearch.PAGES_INDEX, opensearch.CHUNKS_INDEX):
            print(f"opensearch/{index}: {opensearch.count(os_client, index)}",
                  file=sys.stderr)
    else:
        print("opensearch: unreachable", file=sys.stderr)

    q_client = qdrant_client()
    if qdrant_reachable(q_client):
        for collection in (qdrant.PAGES_COLLECTION, qdrant.CHUNKS_COLLECTION):
            print(f"qdrant/{collection}: {qdrant.count(q_client, collection)}",
                  file=sys.stderr)
    else:
        print("qdrant: unreachable", file=sys.stderr)

    with connection() as conn:
        for row in repository.sync_lag(conn):
            print(f"sync {row['index_kind']}/{row['state']}: {row['n']}",
                  file=sys.stderr)
    return 0


def _query(query_text: str, top_k: int | None, as_json: bool) -> int:
    log = get_logger("compendium.query")
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    from compendium.retrieve.pipeline import query as run_query

    result = run_query(query_text)
    pages = result.pages[:top_k] if top_k else result.pages

    if as_json:
        import json

        print(
            json.dumps(
                {
                    "query": result.query_text,
                    "coverage_score": result.coverage_score,
                    "fallback_to_chunks": result.fallback_to_chunks,
                    "pages": [
                        {
                            "id": p.entity_id,
                            "title": p.title,
                            "slug": p.slug,
                            "kind": p.kind,
                            "status": p.status,
                            "score": p.score,
                        }
                        for p in pages
                    ],
                    "citations": [
                        {
                            "id": c.entity_id,
                            "source_title": c.source_title,
                            "position": c.position,
                            "score": c.score,
                            "preview": c.preview,
                        }
                        for c in result.citations
                    ],
                    "gaps": result.gaps,
                },
                indent=2,
            )
        )
    else:
        print(
            f"query: {len(pages)} page(s), coverage {result.coverage_score:.3f}"
            f"{', chunk fallback' if result.fallback_to_chunks else ''}",
            file=sys.stderr,
        )
        for rank, p in enumerate(pages, start=1):
            flag = " [draft]" if p.status == "draft" else ""
            print(
                f"  {rank}. {p.title} ({p.kind}, {p.slug}){flag}  score={p.score:.5f}"
            )
        if result.fallback_to_chunks:
            print("  citations (chunk fallback):", file=sys.stderr)
            for c in result.citations:
                src = c.source_title or c.entity_id
                print(f"    - {src} #{c.position}: {c.preview}")

    log.info(
        "query",
        pages=len(pages),
        coverage=result.coverage_score,
        fallback=result.fallback_to_chunks,
    )
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

    synth_parser = subparsers.add_parser(
        "synth", help="synthesize a concept or topic page"
    )
    synth_parser.add_argument("kind", choices=["concept", "topic"])
    synth_parser.add_argument("name", help="the concept or topic name")
    synth_parser.add_argument(
        "--alias", action="append", default=[], dest="aliases",
        help="an alternate phrasing (repeatable)",
    )

    reindex_parser = subparsers.add_parser(
        "reindex", help="rebuild a derived index from PostgreSQL and the vault"
    )
    reindex_parser.add_argument("target", choices=["pages", "chunks", "all"])

    index_parser = subparsers.add_parser("index", help="derived-index operations")
    index_parser.add_argument(
        "action", choices=["sync", "status"],
        help="sync: drain the pending queue; status: counts and sync lag",
    )

    query_parser = subparsers.add_parser(
        "query", help="page-first retrieval: return ranked wiki pages"
    )
    query_parser.add_argument("text", help="the natural-language query")
    query_parser.add_argument(
        "--top-k", type=int, default=None, help="number of pages to show"
    )
    query_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="machine-readable output"
    )

    args = parser.parse_args(argv)

    if args.command == "ingest":
        return _ingest(args.path, args.kind, args.mine)
    if args.command == "lint":
        return _lint()
    if args.command == "pages":
        return _pages_build()
    if args.command == "synth":
        return _synth(args.kind, args.name, args.aliases)
    if args.command == "reindex":
        return _reindex(args.target)
    if args.command == "index":
        return _index_sync() if args.action == "sync" else _index_status()
    if args.command == "query":
        return _query(args.text, args.top_k, args.as_json)
    return _startup()


if __name__ == "__main__":
    sys.exit(main())
