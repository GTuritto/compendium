"""Application entrypoint: ``python -m compendium [<command> ...]``.

With no subcommand, loads and validates configuration, reports startup, and
exits. Each subcommand handler is parse-call-render-print: it calls a module,
passes the result object to :mod:`compendium.cli.render`, and prints the
rendered payload to stdout. Read commands accept ``--format text|json``.
``structlog`` remains the operational channel on stderr.
"""

from __future__ import annotations

import argparse
import sys

from compendium.cli import render
from compendium.config import ConfigError, load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.ingest.pipeline import ingest
from compendium.logging import get_logger
from compendium.wiki.lint import errors_only, lint_vault, load_vault_pages
from compendium.wiki.source_page import generate_source_page
from compendium.wiki.synth import SynthesisError, synthesize_concept, synthesize_topic

_SOURCE_KINDS = ["book", "article", "paper", "note", "web"]


def _config_error(exc: ConfigError) -> int:
    print(f"Configuration error: {exc}", file=sys.stderr)
    return 1


def _startup() -> int:
    log = get_logger("compendium")
    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)
    log.info("Compendium starting", **config.storage_urls())
    return 0


def _ingest(path: str, kind: str, mine: bool, fmt: str) -> int:
    log = get_logger("compendium.ingest")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    results = ingest(path, kind=kind, mine=mine)
    for result in results:
        log.info(
            "ingested",
            path=result.path,
            status=result.status,
            chunks=result.chunk_count,
            detail=result.detail,
        )
    print(render.ingest(results, fmt))
    failed = sum(1 for r in results if r.status == "failed")
    return 1 if failed and failed == len(results) else 0


def _lint(fmt: str) -> int:
    log = get_logger("compendium.lint")
    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)

    pages, issues = load_vault_pages(config.vault_path)
    source_ids: set[str] | None = None
    try:
        with connection() as conn:
            source_ids = {str(sid) for sid in repository.all_source_ids(conn)}
    except Exception as exc:  # lint still runs, minus source-id-resolves
        log.warning("lint: source-id-resolves skipped", error=str(exc))

    issues = issues + lint_vault(pages, known_source_ids=source_ids)
    errors = errors_only(issues)
    print(render.lint(len(pages), issues, errors, fmt))
    return 1 if errors else 0


def _pages_build() -> int:
    log = get_logger("compendium.pages")
    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)

    built = 0
    with connection() as conn:
        for source_id in repository.sources_without_page(conn):
            page = generate_source_page(conn, source_id, vault_path=config.vault_path)
            if page is not None:
                built += 1
                log.info("source page built", slug=page.slug)
    print(render.pages_build(built))
    return 0


def _synth(kind: str, name: str, aliases: list[str]) -> int:
    log = get_logger("compendium.synth")
    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)

    try:
        with connection() as conn:
            if kind == "concept":
                page = synthesize_concept(
                    conn, name, aliases=aliases, vault_path=config.vault_path
                )
            else:
                page = synthesize_topic(conn, name, vault_path=config.vault_path)
    except SynthesisError as exc:
        print(f"Synthesis error: {exc}", file=sys.stderr)
        return 1

    log.info("synthesized", kind=kind, slug=page.slug)
    print(render.synth(kind, page.slug))
    return 0


def _reindex(target: str, fmt: str) -> int:
    log = get_logger("compendium.reindex")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.index.sync import reindex

    report = reindex(target)
    log.info(
        "reindex", target=target,
        indexed=report.indexed, failed=report.failed, skipped=report.skipped,
    )
    print(render.sync(report, f"reindex {target}", fmt))
    return 1 if report.failed else 0


def _index_sync(fmt: str) -> int:
    log = get_logger("compendium.index")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.index.sync import sync_pending

    report = sync_pending()
    log.info(
        "index sync",
        indexed=report.indexed, failed=report.failed, skipped=report.skipped,
    )
    print(render.sync(report, "index sync", fmt))
    return 1 if report.failed else 0


def _index_status(fmt: str) -> int:
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.index.sync import status

    print(render.index_status(status(), fmt))
    return 0


def _query(query_text: str, top_k: int | None, fmt: str) -> int:
    log = get_logger("compendium.query")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.retrieve.pipeline import query as run_query

    result = run_query(query_text)
    pages = result.pages[:top_k] if top_k else result.pages
    print(render.query(result, pages, fmt))
    log.info(
        "query",
        pages=len(pages),
        coverage=result.coverage_score,
        fallback=result.fallback_to_chunks,
    )
    return 0


def _graph_link(from_slug: str, to_slug: str, edge_type: str) -> int:
    log = get_logger("compendium.graph")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)
    from compendium.graph.links import LinkError, link

    try:
        link(from_slug, to_slug, edge_type)
    except LinkError as exc:
        print(f"link error: {exc}", file=sys.stderr)
        return 1
    log.info("graph link", **{"from": from_slug, "to": to_slug, "type": edge_type})
    print(render.graph_link(from_slug, to_slug, edge_type))
    return 0


def _graph(action: str, fmt: str) -> int:
    log = get_logger("compendium.graph")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.graph.client import graph_connection, graph_reachable

    with graph_connection() as driver:
        reachable = graph_reachable(driver)
    if not reachable:
        print("memgraph: unreachable", file=sys.stderr)
        return 1

    from compendium.graph.rebuild import rebuild, status

    report = rebuild() if action == "rebuild" else status()
    log.info("graph", action=action, nodes=report.nodes, edges=report.edges)
    print(render.graph(report, action, fmt))
    return 0


def _trace(action: str, trace_id: str | None, persist: bool, fmt: str) -> int:
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    if action == "list":
        with connection() as conn:
            rows = repository.list_query_traces(conn)
        print(render.trace_list(rows, fmt))
        return 0

    if action == "show":
        with connection() as conn:
            t = repository.get_query_trace(conn, trace_id)
        if t is None:
            print(f"trace not found: {trace_id}", file=sys.stderr)
            return 1
        print(render.trace_show(t))
        return 0

    # replay
    from compendium.trace.replay import TraceNotFound, replay

    try:
        result = replay(trace_id, persist=persist)
    except TraceNotFound:
        print(f"trace not found: {trace_id}", file=sys.stderr)
        return 1
    print(render.trace_replay(result, persist, fmt))
    return 0


def _page(action: str, slug: str, args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)

    if action == "revisions":
        with connection() as conn:
            page = repository.resolve_page_by_slug(conn, slug)
            if page is None:
                print(f"page not found: {slug}", file=sys.stderr)
                return 1
            revs = repository.get_page_revisions(conn, page["id"])
        print(render.page_revisions(revs, fmt))
        return 0

    if action == "diff":
        from compendium.trace.revisions import (
            body_diff,
            frontmatter_delta,
            resolve_revision,
        )

        with connection() as conn:
            page = repository.resolve_page_by_slug(conn, slug)
            if page is None:
                print(f"page not found: {slug}", file=sys.stderr)
                return 1
            revs = repository.get_page_revisions(conn, page["id"])
            try:
                ra = repository.get_revision(conn, resolve_revision(revs, args.rev_a)["id"])
                rb = repository.get_revision(conn, resolve_revision(revs, args.rev_b)["id"])
            except ValueError as exc:
                print(f"revision error: {exc}", file=sys.stderr)
                return 1
        bd = body_diff(ra["body"], rb["body"], label_a=args.rev_a, label_b=args.rev_b)
        fd = frontmatter_delta(ra["frontmatter"], rb["frontmatter"])
        print(render.page_diff(bd, fd, args.rev_a, args.rev_b, fmt))
        return 0

    # promote
    from compendium.trace.promote import InvalidTransition, PageNotFound, promote

    try:
        res = promote(slug, args.to_status, vault_path=config.vault_path)
    except PageNotFound:
        print(f"page not found: {slug}", file=sys.stderr)
        return 1
    except InvalidTransition as exc:
        print(f"invalid transition: {exc}", file=sys.stderr)
        return 1
    get_logger("compendium.promote").info(
        "promoted", slug=slug, kind=res.promotion_kind,
        from_status=res.from_status, to_status=res.to_status,
    )
    print(render.promote(res))
    return 0


def _promotions(slug: str | None, fmt: str) -> int:
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)
    with connection() as conn:
        events = repository.list_promotion_events(conn, slug=slug)
    print(render.promotions(events, fmt))
    return 0


def _curate(action: str, signal_id: str | None, fmt: str) -> int:
    log = get_logger("compendium.curate")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    if action == "run":
        from compendium.curate.run import run as curate_run

        report = curate_run()
        log.info(
            "curate run", run_id=report.run_id, inserted=report.inserted,
            by_kind=report.by_kind, skipped=report.skipped_generators,
        )
        print(render.curate_run(report, fmt))
        return 0

    if action == "list":
        with connection() as conn:
            rows = repository.list_open_curation_signals(conn)
        print(render.curate_list(rows, fmt))
        return 0

    # synth
    from compendium.curate.synth import SignalNotFound, SynthError, synth_from_signal

    try:
        slug = synth_from_signal(signal_id)
    except SignalNotFound:
        print(f"signal not found: {signal_id}", file=sys.stderr)
        return 1
    except SynthError as exc:
        print(f"synth error: {exc}", file=sys.stderr)
        return 1
    log.info("curate synth", signal=signal_id, slug=slug)
    print(render.curate_synth(slug))
    return 0


def _tui() -> int:
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)
    from compendium.tui.app import run

    return run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compendium")
    subparsers = parser.add_subparsers(dest="command")

    # Shared --format flag for commands whose output is data to read or pipe.
    fmt = argparse.ArgumentParser(add_help=False)
    fmt.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="output format (default: text)",
    )

    ingest_parser = subparsers.add_parser(
        "ingest", help="ingest a file, URL, or directory", parents=[fmt]
    )
    ingest_parser.add_argument("path", help="file path, URL, or directory")
    ingest_parser.add_argument(
        "--kind", default="article", choices=_SOURCE_KINDS, help="source kind"
    )
    ingest_parser.add_argument(
        "--mine", action="store_true", help="mark the source as authored by you"
    )

    subparsers.add_parser("lint", help="lint the wiki vault", parents=[fmt])

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
        "reindex", help="rebuild a derived index from PostgreSQL and the vault",
        parents=[fmt],
    )
    reindex_parser.add_argument("target", choices=["pages", "chunks", "all"])

    index_parser = subparsers.add_parser(
        "index", help="derived-index operations", parents=[fmt]
    )
    index_parser.add_argument(
        "action", choices=["sync", "status"],
        help="sync: drain the pending queue; status: counts and sync lag",
    )

    graph_parser = subparsers.add_parser("graph", help="Memgraph structural index")
    graph_sub = graph_parser.add_subparsers(dest="graph_action", required=True)
    graph_sub.add_parser("rebuild", help="drop and repopulate from PostgreSQL + vault", parents=[fmt])
    graph_sub.add_parser("status", help="node/edge counts", parents=[fmt])
    graph_link = graph_sub.add_parser("link", help="add a curator semantic edge")
    graph_link.add_argument("from_slug")
    graph_link.add_argument("to_slug")
    graph_link.add_argument(
        "--type", dest="edge_type", required=True,
        choices=["RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS"],
    )

    query_parser = subparsers.add_parser(
        "query", help="page-first retrieval: return ranked wiki pages", parents=[fmt]
    )
    query_parser.add_argument("text", help="the natural-language query")
    query_parser.add_argument(
        "--top-k", type=int, default=None, help="number of pages to show"
    )

    trace_parser = subparsers.add_parser("trace", help="query-trace inspection and replay")
    trace_sub = trace_parser.add_subparsers(dest="trace_action", required=True)
    trace_sub.add_parser("list", help="recent traces", parents=[fmt])
    trace_show = trace_sub.add_parser("show", help="show one trace", parents=[fmt])
    trace_show.add_argument("id", help="trace id")
    trace_replay = trace_sub.add_parser("replay", help="replay a trace and diff", parents=[fmt])
    trace_replay.add_argument("id", help="trace id")
    trace_replay.add_argument(
        "--persist", action="store_true", help="record the replay as a new trace"
    )

    page_parser = subparsers.add_parser("page", help="single-page operations")
    page_sub = page_parser.add_subparsers(dest="page_action", required=True)
    page_rev = page_sub.add_parser("revisions", help="list a page's revisions", parents=[fmt])
    page_rev.add_argument("slug")
    page_diff = page_sub.add_parser("diff", help="diff two revisions of a page", parents=[fmt])
    page_diff.add_argument("slug")
    page_diff.add_argument("rev_a", help="ordinal (1=oldest) or id prefix")
    page_diff.add_argument("rev_b", help="ordinal (1=oldest) or id prefix")
    page_promote = page_sub.add_parser("promote", help="promote/deprecate a page")
    page_promote.add_argument("slug")
    page_promote.add_argument(
        "--to", dest="to_status", required=True, choices=["canonical", "deprecated"]
    )

    promotions_parser = subparsers.add_parser("promotions", help="promotion events")
    promotions_sub = promotions_parser.add_subparsers(dest="promotions_action", required=True)
    promotions_list = promotions_sub.add_parser("list", help="list promotion events", parents=[fmt])
    promotions_list.add_argument("--slug", default=None, help="filter to one page")

    subparsers.add_parser("tui", help="launch the keyboard-driven ops console")

    curate_parser = subparsers.add_parser("curate", help="knowledge-graph curation loop")
    curate_sub = curate_parser.add_subparsers(dest="curate_action", required=True)
    curate_sub.add_parser("run", help="run one slow-loop pass (generate signals)", parents=[fmt])
    curate_sub.add_parser("list", help="list open curation signals", parents=[fmt])
    curate_synth = curate_sub.add_parser("synth", help="synthesize from a signal")
    curate_synth.add_argument("signal_id", help="curation signal id")

    args = parser.parse_args(argv)
    fmt_arg = getattr(args, "format", "text")

    if args.command == "ingest":
        return _ingest(args.path, args.kind, args.mine, fmt_arg)
    if args.command == "lint":
        return _lint(fmt_arg)
    if args.command == "pages":
        return _pages_build()
    if args.command == "synth":
        return _synth(args.kind, args.name, args.aliases)
    if args.command == "reindex":
        return _reindex(args.target, fmt_arg)
    if args.command == "index":
        return _index_sync(fmt_arg) if args.action == "sync" else _index_status(fmt_arg)
    if args.command == "graph":
        if args.graph_action == "link":
            return _graph_link(args.from_slug, args.to_slug, args.edge_type)
        return _graph(args.graph_action, fmt_arg)
    if args.command == "query":
        return _query(args.text, args.top_k, fmt_arg)
    if args.command == "trace":
        return _trace(
            args.trace_action, getattr(args, "id", None),
            getattr(args, "persist", False), fmt_arg,
        )
    if args.command == "page":
        return _page(args.page_action, args.slug, args)
    if args.command == "promotions":
        return _promotions(args.slug, fmt_arg)
    if args.command == "tui":
        return _tui()
    if args.command == "curate":
        return _curate(args.curate_action, getattr(args, "signal_id", None), fmt_arg)
    return _startup()


if __name__ == "__main__":
    sys.exit(main())
