"""The CLI presentation seam.

Every ``compendium`` subcommand calls one function here to turn a module's
result object into the string it prints. Two adapters live behind each
function: ``fmt="text"`` for humans, ``fmt="json"`` for scripts. Formatting
is concentrated here so the handlers in :mod:`compendium.__main__` stay
parse-call-print and the modules return data, not presentation.

Every function is pure (result in, string out) and unit-testable with no
backing stores. The returned string is the command's payload and is printed to
stdout; ``structlog`` remains the operational channel on stderr.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

Format = str  # "text" | "json"


# ---------------------------------------------------------------------------
# json adapter (generic over dataclasses, dict rows, and lists)
# ---------------------------------------------------------------------------


def to_json(payload: Any) -> str:
    """Serialize any result payload as indented JSON.

    Dataclasses (and nested ones) become objects via ``asdict``; psycopg dict
    rows pass through; ``default=str`` carries datetimes, UUIDs, and the like.
    """
    if is_dataclass(payload) and not isinstance(payload, type):
        payload = asdict(payload)
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# scalar formatters — shared by the CLI renderers below and the TUI screens
# (compendium/tui/screens/*), so each format lives in exactly one place.
# ---------------------------------------------------------------------------


def fmt_coverage(score: float | None) -> str:
    """A coverage score to three places, or ``-`` when absent."""
    return f"{score:.3f}" if score is not None else "-"


def fmt_ts(dt: Any) -> str:
    """A timestamp as ``YYYY-MM-DD HH:MM``, or ``-`` when absent."""
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


def fmt_fallback(flag: bool) -> str:
    """The list/dashboard fallback flag: ``fallback`` or ``ok``."""
    return "fallback" if flag else "ok"


def fmt_fallback_suffix(flag: bool) -> str:
    """The query-summary fallback suffix: ``, chunk fallback`` or empty."""
    return ", chunk fallback" if flag else ""


def fmt_payload(payload: Any, limit: int = 60) -> str:
    """A signal payload as truncated compact JSON, or empty when absent."""
    return json.dumps(payload)[:limit] if payload else ""


def _aligned(columns: list[str], rows: list[list[str]]) -> str:
    """A simple left-aligned text table; empty body renders as the header only."""
    widths = [len(c) for c in columns]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*columns).rstrip()]
    lines += [fmt.format(*row).rstrip() for row in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# action commands (reports / summaries)
# ---------------------------------------------------------------------------


def ingest(results: list[Any], fmt: Format = "text") -> str:
    stored = sum(1 for r in results if r.status in ("ingested", "updated"))
    unchanged = sum(1 for r in results if r.status == "unchanged")
    failed = sum(1 for r in results if r.status == "failed")
    if fmt == "json":
        return to_json(
            {
                "total": len(results),
                "stored": stored,
                "unchanged": unchanged,
                "failed": failed,
                "results": [asdict(r) for r in results],
            }
        )
    return (
        f"{len(results)} source(s): {stored} stored, "
        f"{unchanged} unchanged, {failed} failed"
    )


def lint(page_count: int, issues: list[Any], errors: list[Any], fmt: Format = "text") -> str:
    warnings = len(issues) - len(errors)
    if fmt == "json":
        return to_json(
            {
                "pages": page_count,
                "errors": len(errors),
                "warnings": warnings,
                "issues": [asdict(i) for i in issues],
            }
        )
    lines = [
        f"  {i.severity}: [{i.page}] {i.rule}: {i.message}" for i in issues
    ]
    lines.append(
        f"lint: {page_count} page(s), {len(errors)} error(s), {warnings} warning(s)"
    )
    return "\n".join(lines)


def pages_build(built: int, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json({"built": built})
    return f"pages build: {built} source page(s) generated"


def synth(kind: str, slug: str, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json({"kind": kind, "slug": slug})
    return f"synth: wrote {kind} page '{slug}'"


def sync(report: Any, label: str, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(report)
    lines = [f"  failed: {e}" for e in report.errors]
    lines.append(
        f"{label}: {report.indexed} indexed, {report.failed} failed, "
        f"{report.skipped} skipped"
    )
    return "\n".join(lines)


def index_status(report: Any, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(report)
    lines: list[str] = []
    if report.opensearch is None:
        lines.append("opensearch: unreachable")
    else:
        for index, n in report.opensearch.items():
            lines.append(f"opensearch/{index}: {n}")
    if report.qdrant is None:
        lines.append("qdrant: unreachable")
    else:
        for collection, n in report.qdrant.items():
            lines.append(f"qdrant/{collection}: {n}")
    for row in report.sync_lag:
        lines.append(f"sync {row['index_kind']}/{row['state']}: {row['n']}")
    return "\n".join(lines)


def graph_link(from_slug: str, to_slug: str, edge_type: str, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json({"from": from_slug, "to": to_slug, "type": edge_type})
    return f"graph link: {from_slug} -[{edge_type}]-> {to_slug}"


def graph(report: Any, action: str, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(report)
    lines = [f"node {label}: {n}" for label, n in report.nodes.items()]
    for etype, n in report.edges.items():
        if n or action == "status":
            lines.append(f"edge {etype}: {n}")
    lines.append(
        f"graph {action}: {sum(report.nodes.values())} node(s), "
        f"{sum(report.edges.values())} edge(s)"
    )
    return "\n".join(lines)


def graph_backfill(count: int, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json({"captured": count})
    return f"graph backfill-edges: captured {count} semantic edge(s) into PostgreSQL"


def promote(res: Any, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(res)
    return (
        f"promoted {res.slug}: {res.from_status} -> {res.to_status} "
        f"({res.promotion_kind})"
    )


def curate_run(report: Any, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(report)
    lines = [f"  {kind}: {n}" for kind, n in report.by_kind.items()]
    if report.skipped_generators:
        lines.append(
            f"  skipped (memgraph down): {', '.join(report.skipped_generators)}"
        )
    lines.append(
        f"curate run: {report.inserted} new signal(s) [run {report.run_id}]"
    )
    return "\n".join(lines)


def curate_synth(slug: str, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json({"slug": slug})
    return f"curate synth: drafted '{slug}' (signal in_progress)"


# ---------------------------------------------------------------------------
# read commands (queries / listings)
# ---------------------------------------------------------------------------


def query(result: Any, pages: list[Any], fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(
            {
                "query": result.query_text,
                "coverage_score": result.coverage_score,
                "fallback_to_chunks": result.fallback_to_chunks,
                "pages": [asdict(p) for p in pages],
                "citations": [asdict(c) for c in result.citations],
                "gaps": result.gaps,
            }
        )
    lines = [
        f"query: {len(pages)} page(s), coverage {fmt_coverage(result.coverage_score)}"
        f"{fmt_fallback_suffix(result.fallback_to_chunks)}"
    ]
    for rank, p in enumerate(pages, start=1):
        flag = " [draft]" if p.status == "draft" else ""
        lines.append(f"  {rank}. {p.title} ({p.kind}, {p.slug}){flag}  score={p.score:.5f}")
    if result.fallback_to_chunks:
        lines.append("  citations (chunk fallback):")
        for c in result.citations:
            src = c.source_title or c.entity_id
            lines.append(f"    - {src} #{c.position}: {c.preview}")
    return "\n".join(lines)


def ask(result: Any, fmt: Format = "text", *, answer_streamed: bool = False) -> str:
    """Render an ``AskResult`` (v0.2 Phase 6).

    ``--format json`` emits the full structured object. In text mode a refusal
    prints the gap and suggested actions; a composed answer prints the answer
    (unless ``answer_streamed``, when it was already streamed to stdout by the
    handler), then the citation block and the trace footer.
    """
    if fmt == "json":
        return to_json(
            {
                "answer": result.answer,
                "refused": result.refused,
                "citations": [asdict(c) for c in result.citations],
                "coverage_score": result.coverage_score,
                "trace_id": result.trace_id,
                "ask_trace_id": result.ask_trace_id,
                "gap": result.gap,
                "suggested_actions": result.suggested_actions,
            }
        )

    footer = (
        f"coverage {fmt_coverage(result.coverage_score)}  "
        f"trace {result.trace_id or '-'}  ask_trace {result.ask_trace_id or '-'}"
    )
    if result.refused:
        lines = ["refused: coverage below threshold (no answer composed)"]
        if result.gap:
            lines.append(f"  gap: {fmt_payload(result.gap)}")
        if result.suggested_actions:
            lines.append("  suggested actions:")
            lines += [f"    - {a}" for a in result.suggested_actions]
        lines.append(footer)
        return "\n".join(lines)

    lines = []
    if not answer_streamed:
        lines.append(result.answer or "")
    lines.append("citations:")
    for c in result.citations:
        lines.append(f"  {c.ref} {c.title} ({c.slug})  trace_rank={c.trace_rank}")
    lines.append(footer)
    return "\n".join(lines)


def trace_list(rows: list[dict], fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(rows)
    lines = []
    for r in rows:
        lines.append(
            f"  {r['id']}  cov={fmt_coverage(r['coverage_score'])}  "
            f"{fmt_fallback(r['fallback_to_chunks'])}  gaps={r['gap_count']}  "
            f"{fmt_ts(r['created_at'])}  {r['query_text'][:50]}"
        )
    return "\n".join(lines)


def trace_show(t: dict, fmt: Format = "text") -> str:
    payload = {
        "id": str(t["id"]),
        "query_text": t["query_text"],
        "coverage_score": t["coverage_score"],
        "fallback_to_chunks": t["fallback_to_chunks"],
        "corpus_revision": t["corpus_revision"],
        "final_ranking": t["final_ranking"],
        "gaps": t["gaps"],
        "latencies_ms": t["latencies_ms"],
        "pipeline": t["pipeline"],
    }
    # show is JSON in both modes; the trace is structured data.
    return to_json(payload)


def trace_replay(result: Any, persisted: bool, fmt: Format = "text") -> str:
    d = result.diff
    if fmt == "json":
        return to_json(
            {
                "trace_id": result.trace_id,
                "query_text": result.query_text,
                "original_coverage": result.original_coverage,
                "replayed_coverage": result.replayed_coverage,
                "coverage_delta": d.coverage_delta,
                "fallback_changed": d.fallback_changed,
                "unchanged": d.unchanged,
                "added": d.added,
                "removed": d.removed,
                "moved": d.moved,
                "persisted": persisted,
            }
        )
    orig = result.original_coverage
    lines = [f'replay {result.trace_id}: "{result.query_text}"']
    lines.append(
        f"  coverage {orig} -> {result.replayed_coverage:.3f} "
        f"(delta {d.coverage_delta:+.3f})"
        f"{' [fallback changed]' if d.fallback_changed else ''}"
    )
    if d.unchanged:
        lines.append("  ranking unchanged")
    for a in d.added:
        lines.append(f"  + {a['title']} (now rank {a['rank']})")
    for r in d.removed:
        lines.append(f"  - {r['title']} (was rank {r['rank']})")
    for m in d.moved:
        lines.append(f"  ~ {m['title']} (rank {m['from_rank']} -> {m['to_rank']})")
    if persisted:
        lines.append("  (persisted a new trace)")
    return "\n".join(lines)


def page_revisions(rows: list[dict], fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(rows)
    lines = []
    for i, r in enumerate(rows, start=1):
        note = f"  {r['notes']}" if r["notes"] else ""
        lines.append(
            f"  {i}. {r['id']}  {r['generator']}  {fmt_ts(r['created_at'])}{note}"
        )
    return "\n".join(lines)


def page_diff(body: str, fdelta: Any, rev_a: str, rev_b: str, fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(
            {
                "rev_a": rev_a,
                "rev_b": rev_b,
                "body_diff": body,
                "frontmatter": {
                    "added": fdelta.added,
                    "removed": fdelta.removed,
                    "changed": {k: list(v) for k, v in fdelta.changed.items()},
                },
            }
        )
    lines = [body if body else "  (body unchanged)"]
    if fdelta.empty:
        lines.append("  (frontmatter unchanged)")
    else:
        for k, v in fdelta.added.items():
            lines.append(f"  frontmatter + {k}: {v}")
        for k, v in fdelta.removed.items():
            lines.append(f"  frontmatter - {k}: {v}")
        for k, (old, new) in fdelta.changed.items():
            lines.append(f"  frontmatter ~ {k}: {old} -> {new}")
    return "\n".join(lines)


def promotions(events: list[dict], fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(events)
    lines = [
        f"  {fmt_ts(e['created_at'])}  {e['kind']}  {e['page_kind']}/{e['slug']}"
        for e in events
    ]
    lines.append(f"promotions: {len(events)} event(s)")
    return "\n".join(lines)


def curate_list(rows: list[dict], fmt: Format = "text") -> str:
    if fmt == "json":
        return to_json(rows)
    lines = [
        f"  [{r['priority']}] {r['kind']}  {fmt_payload(r['payload'])}"
        for r in rows
    ]
    lines.append(f"curate list: {len(rows)} open signal(s)")
    return "\n".join(lines)
