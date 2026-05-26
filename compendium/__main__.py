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


def _graph(action: str) -> int:
    log = get_logger("compendium.graph")
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    from compendium.graph.client import graph_driver, graph_reachable

    driver = graph_driver()
    try:
        reachable = graph_reachable(driver)
    finally:
        driver.close()
    if not reachable:
        print("memgraph: unreachable", file=sys.stderr)
        return 1

    from compendium.graph.rebuild import rebuild, status

    report = rebuild() if action == "rebuild" else status()
    for label, n in report.nodes.items():
        print(f"node {label}: {n}", file=sys.stderr)
    for etype, n in report.edges.items():
        if n or action == "status":
            print(f"edge {etype}: {n}", file=sys.stderr)
    log.info("graph", action=action, nodes=report.nodes, edges=report.edges)
    print(
        f"graph {action}: {sum(report.nodes.values())} node(s), "
        f"{sum(report.edges.values())} edge(s)",
        file=sys.stderr,
    )
    return 0


def _trace(action: str, trace_id: str | None, persist: bool) -> int:
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    if action == "list":
        with connection() as conn:
            rows = repository.list_query_traces(conn)
        for r in rows:
            cov = f"{r['coverage_score']:.3f}" if r["coverage_score"] is not None else "-"
            fb = "fallback" if r["fallback_to_chunks"] else "ok"
            print(f"  {r['id']}  cov={cov}  {fb}  gaps={r['gap_count']}  "
                  f"{r['created_at']:%Y-%m-%d %H:%M}  {r['query_text'][:50]}",
                  file=sys.stderr)
        return 0

    if action == "show":
        with connection() as conn:
            t = repository.get_query_trace(conn, trace_id)
        if t is None:
            print(f"trace not found: {trace_id}", file=sys.stderr)
            return 1
        import json
        print(json.dumps({
            "id": str(t["id"]), "query_text": t["query_text"],
            "coverage_score": t["coverage_score"],
            "fallback_to_chunks": t["fallback_to_chunks"],
            "corpus_revision": t["corpus_revision"],
            "final_ranking": t["final_ranking"], "gaps": t["gaps"],
            "latencies_ms": t["latencies_ms"], "pipeline": t["pipeline"],
        }, indent=2, default=str))
        return 0

    # replay
    from compendium.trace.replay import replay, TraceNotFound
    try:
        result = replay(trace_id, persist=persist)
    except TraceNotFound:
        print(f"trace not found: {trace_id}", file=sys.stderr)
        return 1
    d = result.diff
    print(f"replay {result.trace_id}: \"{result.query_text}\"", file=sys.stderr)
    print(f"  coverage {result.original_coverage} -> {result.replayed_coverage:.3f} "
          f"(delta {d.coverage_delta:+.3f}){' [fallback changed]' if d.fallback_changed else ''}",
          file=sys.stderr)
    if d.unchanged:
        print("  ranking unchanged", file=sys.stderr)
    for a in d.added:
        print(f"  + {a['title']} (now rank {a['rank']})", file=sys.stderr)
    for r in d.removed:
        print(f"  - {r['title']} (was rank {r['rank']})", file=sys.stderr)
    for m in d.moved:
        print(f"  ~ {m['title']} (rank {m['from_rank']} -> {m['to_rank']})", file=sys.stderr)
    if persist:
        print("  (persisted a new trace)", file=sys.stderr)
    return 0


def _page(action: str, slug: str, args: argparse.Namespace) -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    if action == "revisions":
        with connection() as conn:
            page = repository.resolve_page_by_slug(conn, slug)
            if page is None:
                print(f"page not found: {slug}", file=sys.stderr)
                return 1
            revs = repository.get_page_revisions(conn, page["id"])
        for i, r in enumerate(revs, start=1):
            note = f"  {r['notes']}" if r["notes"] else ""
            print(f"  {i}. {r['id']}  {r['generator']}  {r['created_at']:%Y-%m-%d %H:%M}{note}",
                  file=sys.stderr)
        return 0

    if action == "diff":
        from compendium.trace.revisions import body_diff, frontmatter_delta, resolve_revision
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
        print(bd if bd else "  (body unchanged)")
        if fd.empty:
            print("  (frontmatter unchanged)", file=sys.stderr)
        else:
            for k, v in fd.added.items():
                print(f"  frontmatter + {k}: {v}", file=sys.stderr)
            for k, v in fd.removed.items():
                print(f"  frontmatter - {k}: {v}", file=sys.stderr)
            for k, (old, new) in fd.changed.items():
                print(f"  frontmatter ~ {k}: {old} -> {new}", file=sys.stderr)
        return 0

    # promote
    from compendium.trace.promote import promote, InvalidTransition, PageNotFound
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
    print(f"promoted {slug}: {res.from_status} -> {res.to_status} ({res.promotion_kind})",
          file=sys.stderr)
    return 0


def _promotions(slug: str | None) -> int:
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    with connection() as conn:
        events = repository.list_promotion_events(conn, slug=slug)
    for e in events:
        print(f"  {e['created_at']:%Y-%m-%d %H:%M}  {e['kind']}  "
              f"{e['page_kind']}/{e['slug']}", file=sys.stderr)
    print(f"promotions: {len(events)} event(s)", file=sys.stderr)
    return 0


def _tui() -> int:
    try:
        load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    from compendium.tui.app import run

    return run()


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

    graph_parser = subparsers.add_parser("graph", help="Memgraph structural index")
    graph_parser.add_argument(
        "action", choices=["rebuild", "status"],
        help="rebuild: drop and repopulate from PostgreSQL + vault; "
             "status: node/edge counts",
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

    trace_parser = subparsers.add_parser("trace", help="query-trace inspection and replay")
    trace_sub = trace_parser.add_subparsers(dest="trace_action", required=True)
    trace_sub.add_parser("list", help="recent traces")
    trace_show = trace_sub.add_parser("show", help="show one trace")
    trace_show.add_argument("id", help="trace id")
    trace_replay = trace_sub.add_parser("replay", help="replay a trace and diff")
    trace_replay.add_argument("id", help="trace id")
    trace_replay.add_argument(
        "--persist", action="store_true", help="record the replay as a new trace"
    )

    page_parser = subparsers.add_parser("page", help="single-page operations")
    page_sub = page_parser.add_subparsers(dest="page_action", required=True)
    page_rev = page_sub.add_parser("revisions", help="list a page's revisions")
    page_rev.add_argument("slug")
    page_diff = page_sub.add_parser("diff", help="diff two revisions of a page")
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
    promotions_list = promotions_sub.add_parser("list", help="list promotion events")
    promotions_list.add_argument("--slug", default=None, help="filter to one page")

    subparsers.add_parser("tui", help="launch the keyboard-driven ops console")

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
    if args.command == "graph":
        return _graph(args.action)
    if args.command == "query":
        return _query(args.text, args.top_k, args.as_json)
    if args.command == "trace":
        return _trace(args.trace_action, getattr(args, "id", None),
                      getattr(args, "persist", False))
    if args.command == "page":
        return _page(args.page_action, args.slug, args)
    if args.command == "promotions":
        return _promotions(args.slug)
    if args.command == "tui":
        return _tui()
    return _startup()


if __name__ == "__main__":
    sys.exit(main())
