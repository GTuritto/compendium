"""Application entrypoint: ``python -m compendium [<command> ...]``.

With no subcommand, loads and validates configuration, reports startup, and
exits. Each subcommand handler is parse-call-render-print: it calls a module,
passes the result object to :mod:`compendium.cli.render`, and prints the
rendered payload to stdout. Read commands accept ``--format text|json``.
``structlog`` remains the operational channel on stderr.
"""

from __future__ import annotations

import argparse
import os
import sys

from compendium.backup import BackupError, RestoreError, run_backup, run_restore
from compendium.backup import ScheduleError as BackupScheduleError
from compendium.backup import install_schedule as install_backup_schedule
from compendium.backup import uninstall_schedule as uninstall_backup_schedule
from compendium.inbox import (
    InboxError,
    create_layout as inbox_create_layout,
    install_watcher as install_inbox_watcher,
    process_inbox,
    read_status as read_inbox_status,
    uninstall_watcher as uninstall_inbox_watcher,
)
from compendium.schedule import (
    ScheduleError,
    install_schedule,
    parse_interval,
    read_status,
    uninstall_schedule,
)
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


def _ask(question: str, fmt: str) -> int:
    log = get_logger("compendium.ask")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.answer import ask as run_ask

    if fmt == "json":
        result = run_ask(question)
        print(render.ask(result, "json"))
    else:
        # Text mode streams the composed answer to stdout as it arrives; the
        # footer (citations + trace ids) prints after. A refusal streams
        # nothing, so the renderer prints the full refusal block.
        streamed: list[str] = []

        def on_token(token: str) -> None:
            sys.stdout.write(token)
            sys.stdout.flush()
            streamed.append(token)

        result = run_ask(question, on_token=on_token)
        if streamed:
            sys.stdout.write("\n")
        print(render.ask(result, "text", answer_streamed=bool(streamed)))
    log.info(
        "ask",
        refused=result.refused,
        coverage=result.coverage_score,
        citations=len(result.citations),
        ask_trace=result.ask_trace_id or None,
    )
    return 0


def _serve(action: str | None, host: str, port: int, fmt: str) -> int:
    log = get_logger("compendium.serve")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.api import service

    if action == "install":
        try:
            result = service.install_service(host=host, port=port)
        except service.ServiceError as exc:
            print(f"serve install failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"serve install: {result.path} ({result.detail})")
        return 0
    if action == "uninstall":
        result = service.uninstall_service()
        print(f"serve uninstall: {result.path} ({result.detail})")
        return 0
    if action == "status":
        status = service.read_status()
        if fmt == "json":
            print(render.to_json(status.to_dict()))
        else:
            print(
                f"serve: loaded={status.loaded} state={status.state} "
                f"host={status.host} port={status.port}\n  unit: {status.unit_path}"
            )
        return 0 if status.loaded else 1

    # No subcommand: run the server in the foreground.
    from compendium.api.http import run as run_http

    log.info("serve starting", host=host, port=port)
    run_http(host=host, port=port)
    return 0


def _mcp() -> int:
    log = get_logger("compendium.mcp")
    try:
        load_config()
    except ConfigError as exc:
        return _config_error(exc)

    from compendium.api.mcp import run as run_mcp

    log.info("mcp stdio server starting")
    run_mcp()
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


def _graph_backfill(fmt: str) -> int:
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

    from compendium.graph.semantic_edges import backfill_edges

    count = backfill_edges()
    log.info("graph backfill-edges", captured=count)
    print(render.graph_backfill(count, fmt))
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


def _backup(action: str | None, at: str) -> int:
    if action in (None, "run"):
        try:
            config = load_config()
        except ConfigError as exc:
            return _config_error(exc)
        try:
            local_dir = run_backup(config)
        except BackupError as exc:
            print(f"backup failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            if exc.local_dir is not None:
                print(f"local backup retained at {exc.local_dir}", file=sys.stderr)
            return 1
        print(f"backup: wrote {local_dir}")
        return 0
    if action == "install":
        try:
            result = install_backup_schedule(at)
        except BackupScheduleError as exc:
            print(f"backup install failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"backup install: {result.path} ({result.detail})")
        return 0
    if action == "uninstall":
        try:
            result = uninstall_backup_schedule()
        except BackupScheduleError as exc:
            print(f"backup uninstall failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"backup uninstall: {result.path} ({result.detail})")
        return 0
    print(f"unknown backup action: {action}", file=sys.stderr)
    return 1


def _inbox(action: str | None, path_arg: str | None, fmt: str = "text") -> int:
    from pathlib import Path

    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)
    resolved_path = Path(path_arg or config.inbox_path).expanduser().resolve()

    if action == "install":
        try:
            inbox_create_layout(resolved_path)
            result = install_inbox_watcher(resolved_path)
        except InboxError as exc:
            print(f"inbox install failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"inbox install: {resolved_path}")
        print(f"  watcher: {result.path} ({result.detail})")
        return 0
    if action == "uninstall":
        try:
            result = uninstall_inbox_watcher()
        except InboxError as exc:
            print(f"inbox uninstall failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"inbox uninstall: {result.path} ({result.detail})")
        return 0
    if action == "process":
        try:
            report = process_inbox(resolved_path)
        except Exception as exc:
            print(f"inbox process: systemic failure: {exc}", file=sys.stderr)
            return 1
        print(f"inbox process: {report}")
        return 0 if not report.errored else 1
    if action == "status":
        status = read_inbox_status(resolved_path)
        if fmt == "json":
            import json
            print(json.dumps(status.to_dict(), indent=2))
        else:
            waiting_total = sum(status.waiting.values())
            print(f"inbox status: {resolved_path}")
            print(f"  watcher_loaded: {status.watcher_loaded}")
            print(f"  waiting:        {waiting_total} total")
            for kind, n in status.waiting.items():
                if n:
                    print(f"    {kind}: {n}")
            print(f"  processed:      today={status.processed_today} yesterday={status.processed_yesterday}")
            print(f"  failed:         today={status.failed_today} yesterday={status.failed_yesterday}")
            print(
                f"  most_recent_processed: "
                f"{status.most_recent_processed.isoformat() if status.most_recent_processed else '(none)'}"
            )
            print(
                f"  most_recent_failed:    "
                f"{status.most_recent_failed.isoformat() if status.most_recent_failed else '(none)'}"
            )
        return 0
    print(f"unknown inbox action: {action}", file=sys.stderr)
    return 1


def _schedule(action: str | None, every: str, fmt: str = "text") -> int:
    if action == "install":
        try:
            interval = parse_interval(every)
        except ScheduleError as exc:
            print(f"schedule install failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        try:
            result = install_schedule(interval)
        except ScheduleError as exc:
            print(f"schedule install failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"schedule install: {result.path} ({result.detail})")
        return 0
    if action == "uninstall":
        try:
            result = uninstall_schedule()
        except ScheduleError as exc:
            print(f"schedule uninstall failed at step {exc.step}: {exc.detail}", file=sys.stderr)
            return 1
        print(f"schedule uninstall: {result.path} ({result.detail})")
        return 0
    if action == "status":
        status = read_status()
        if fmt == "json":
            import json
            print(json.dumps(status.to_dict(), indent=2))
        else:
            print(f"schedule: loaded={status.loaded} state={status.state}")
            print(f"  unit_path: {status.unit_path}")
            if status.interval_seconds is not None:
                print(f"  interval:  {status.interval_seconds}s")
            print(f"  last_fired: {status.last_fired or '(unknown)'}")
            print(f"  next_fire:  {status.next_fire or '(unknown)'}")
        return 0 if status.loaded else 1
    print(f"unknown schedule action: {action}", file=sys.stderr)
    return 1


def _restore(timestamp: str, force: bool) -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        return _config_error(exc)
    try:
        run_restore(config, timestamp, force=force)
    except RestoreError as exc:
        print(f"restore failed at step {exc.step}: {exc.detail}", file=sys.stderr)
        return 1
    print(
        "restore: complete. "
        "Run 'compendium reindex all' and 'compendium graph rebuild' "
        "to repopulate the derived stores."
    )
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
    parser.add_argument(
        "--profile", action="store_true",
        help="profile this invocation with cProfile: writes a .prof artifact to "
             "~/.compendium/profiles (COMPENDIUM_PROFILE_DIR overrides) and "
             "prints a top-25 cumulative summary",
    )
    parser.add_argument(
        "--timings", action="store_true",
        help="enable timed-span logging for this invocation (same as "
             "COMPENDIUM_PROFILE=1 in the environment or .env)",
    )
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
    graph_sub.add_parser(
        "backfill-edges",
        help="capture current in-graph semantic edges into PostgreSQL (one-shot, idempotent)",
        parents=[fmt],
    )
    graph_link = graph_sub.add_parser("link", help="add a curator semantic edge")
    graph_link.add_argument("from_slug")
    graph_link.add_argument("to_slug")
    from compendium.graph.edge_type import CURATOR_SETTABLE_EDGES

    graph_link.add_argument(
        "--type", dest="edge_type", required=True,
        choices=list(CURATOR_SETTABLE_EDGES),
    )

    query_parser = subparsers.add_parser(
        "query", help="page-first retrieval: return ranked wiki pages", parents=[fmt]
    )
    query_parser.add_argument("text", help="the natural-language query")
    query_parser.add_argument(
        "--top-k", type=int, default=None, help="number of pages to show"
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="composed answer over the top pages, with citations (v0.2 Phase 6)",
        parents=[fmt],
    )
    ask_parser.add_argument("question", help="the natural-language question")

    serve_parser = subparsers.add_parser(
        "serve",
        help="run the HTTP access surface on 127.0.0.1 (v0.2 Phase 7, ADR-011)",
    )
    serve_parser.add_argument(
        "--host", default="127.0.0.1",
        help="bind host (default 127.0.0.1; non-loopback is a v0.3 concern, no auth)",
    )
    serve_parser.add_argument("--port", type=int, default=8787, help="bind port (default 8787)")
    serve_sub = serve_parser.add_subparsers(dest="serve_action")
    serve_install = serve_sub.add_parser(
        "install", help="install the always-on access-surface unit (launchd/systemd)"
    )
    serve_install.add_argument("--host", default="127.0.0.1")
    serve_install.add_argument("--port", type=int, default=8787)
    serve_sub.add_parser("uninstall", help="remove the access-surface unit (idempotent)")
    serve_sub.add_parser("status", help="report the access-surface unit state", parents=[fmt])

    subparsers.add_parser(
        "mcp",
        help="run the MCP stdio access surface (v0.2 Phase 7, ADR-011)",
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

    backup_parser = subparsers.add_parser(
        "backup",
        help="back up PostgreSQL + the vault (and manage the scheduled unit)",
    )
    backup_sub = backup_parser.add_subparsers(dest="backup_action")
    backup_sub.add_parser(
        "run",
        help="run one backup now (default action when no sub-command is given)",
    )
    backup_install = backup_sub.add_parser(
        "install",
        help="install a daily scheduled backup (launchd on macOS, systemd user timer on Linux)",
    )
    backup_install.add_argument(
        "--at", default="02:00",
        help="firing time HH:MM (24-hour, default 02:00)",
    )
    backup_sub.add_parser(
        "uninstall",
        help="remove the scheduled backup unit (idempotent)",
    )

    restore_parser = subparsers.add_parser(
        "restore",
        help="restore PostgreSQL + the vault from a timestamped backup directory",
    )
    restore_parser.add_argument("timestamp", help="backup timestamp (YYYYMMDDTHHMMSSZ)")
    restore_parser.add_argument(
        "--force", action="store_true",
        help="overwrite an existing non-empty vault",
    )

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="manage the scheduled curation slow loop (launchd on macOS, systemd user timer on Linux)",
    )
    schedule_sub = schedule_parser.add_subparsers(dest="schedule_action", required=True)
    schedule_install = schedule_sub.add_parser(
        "install",
        help="install a scheduled unit that fires `compendium curate run` every <interval>",
    )
    schedule_install.add_argument(
        "--every", default="1h",
        help="firing interval; accepts Nh, Nm, NhMm (default 1h, min 1m, max 7d)",
    )
    schedule_sub.add_parser(
        "uninstall",
        help="remove the scheduled curate unit (idempotent)",
    )
    schedule_sub.add_parser(
        "status",
        help="report loaded state, last/next firing, and interval",
        parents=[fmt],
    )

    inbox_parser = subparsers.add_parser(
        "inbox",
        help="manage the auto-ingestion inbox watcher (launchd on macOS, systemd user .path on Linux)",
    )
    inbox_sub = inbox_parser.add_subparsers(dest="inbox_action", required=True)
    inbox_install = inbox_sub.add_parser(
        "install",
        help="create the inbox layout and install the OS-native watcher unit",
    )
    inbox_install.add_argument(
        "--path", default=None,
        help="inbox path (default: INBOX_PATH from .env, or ~/Compendium/inbox)",
    )
    inbox_uninstall = inbox_sub.add_parser(
        "uninstall",
        help="remove the inbox watcher unit (idempotent); preserves the inbox directory",
    )
    inbox_uninstall.add_argument(
        "--path", default=None,
        help="inbox path (unused for uninstall; accepted for symmetry)",
    )
    inbox_process = inbox_sub.add_parser(
        "process",
        help="scan the inbox, ingest eligible files, route to processed/<date>/ or failed/<date>/",
    )
    inbox_process.add_argument(
        "--path", default=None,
        help="inbox path (default: INBOX_PATH from .env, or ~/Compendium/inbox)",
    )
    inbox_status = inbox_sub.add_parser(
        "status",
        help="report waiting / processed / failed counts and recent file timestamps",
        parents=[fmt],
    )
    inbox_status.add_argument(
        "--path", default=None,
        help="inbox path (default: INBOX_PATH from .env, or ~/Compendium/inbox)",
    )

    curate_parser = subparsers.add_parser("curate", help="knowledge-graph curation loop")
    curate_sub = curate_parser.add_subparsers(dest="curate_action", required=True)
    curate_sub.add_parser("run", help="run one slow-loop pass (generate signals)", parents=[fmt])
    curate_sub.add_parser("list", help="list open curation signals", parents=[fmt])
    curate_synth = curate_sub.add_parser("synth", help="synthesize from a signal")
    curate_synth.add_argument("signal_id", help="curation signal id")

    args = parser.parse_args(argv)
    fmt_arg = getattr(args, "format", "text")

    if args.timings:
        os.environ["COMPENDIUM_PROFILE"] = "1"
    if args.profile:
        # Span logging should fire during a profiled run too.
        os.environ.setdefault("COMPENDIUM_PROFILE", "1")
        from compendium.profiling import cpu_profile

        with cpu_profile(args.command or "compendium"):
            return _dispatch(args, fmt_arg)
    return _dispatch(args, fmt_arg)


def _dispatch(args: argparse.Namespace, fmt_arg: str) -> int:
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
        if args.graph_action == "backfill-edges":
            return _graph_backfill(fmt_arg)
        return _graph(args.graph_action, fmt_arg)
    if args.command == "query":
        return _query(args.text, args.top_k, fmt_arg)
    if args.command == "ask":
        return _ask(args.question, fmt_arg)
    if args.command == "serve":
        return _serve(getattr(args, "serve_action", None), args.host, args.port, fmt_arg)
    if args.command == "mcp":
        return _mcp()
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
    if args.command == "backup":
        return _backup(
            getattr(args, "backup_action", None),
            getattr(args, "at", "02:00"),
        )
    if args.command == "restore":
        return _restore(args.timestamp, args.force)
    if args.command == "schedule":
        return _schedule(
            getattr(args, "schedule_action", None),
            getattr(args, "every", "1h"),
            fmt_arg,
        )
    if args.command == "inbox":
        return _inbox(
            getattr(args, "inbox_action", None),
            getattr(args, "path", None),
            fmt_arg,
        )
    return _startup()


if __name__ == "__main__":
    sys.exit(main())
