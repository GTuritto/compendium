"""MCP transport for the access surface (``compendium mcp``, v0.2 Phase 7).

A FastMCP stdio server over the shared :mod:`compendium.api.facade`, registering
the six verbs as MCP tools. Input schemas are derived by FastMCP from the tool
signatures; each tool returns the shared :func:`compendium.api.serialize.to_payload`
result as a JSON string, so the MCP contract is the same JSON as
``--format json`` and the HTTP transport. ``ask`` streams composition tokens as
MCP log notifications while composing, then returns the structured result.

stdio only in v0.2 (subprocess per agent session; assumes colocation, ADR-011).

Note: this module deliberately does NOT use ``from __future__ import annotations``.
FastMCP evaluates each tool's type hints to build its input schema; keeping the
annotations as real objects (not strings) lets ``Context | None`` resolve in the
scope where ``Context`` is imported.
"""

import json
from typing import Any

import anyio


def build_server() -> Any:
    """Build the FastMCP server over the facade. Imported lazily by ``mcp``.

    Every tool is async and offloads the (blocking, internally-``asyncio.run``-using)
    facade call to a worker thread via ``anyio.to_thread.run_sync`` — running it
    inline would call ``asyncio.run`` inside the already-running MCP event loop.
    """
    from mcp.server.fastmcp import Context, FastMCP

    from compendium.api import facade, to_payload

    server = FastMCP("compendium")

    def _json(obj: Any) -> str:
        return json.dumps(to_payload(obj))

    @server.tool(
        description="Page-first retrieval: ranked wiki pages, coverage, and a trace id."
    )
    async def query(text: str) -> str:
        return await anyio.to_thread.run_sync(lambda: _json(facade.query(text)))

    @server.tool(
        description=(
            "Composed answer over the top-K pages with page-anchored citations; "
            "refuses below the coverage threshold and names the next CLI command."
        )
    )
    async def ask(question: str, ctx: Context | None = None) -> str:
        def on_token(token: str) -> None:
            # Stream each delta as an MCP log notification (best-effort).
            if ctx is not None:
                try:
                    anyio.from_thread.run(ctx.info, token)
                except Exception:
                    pass

        result = await anyio.to_thread.run_sync(
            lambda: facade.ask(question, on_token=on_token)
        )
        return _json(result)

    @server.tool(
        description=(
            "Ingest one source from a file path or base64 bytes (with a filename "
            "hint); auto-runs index sync so the source is immediately queryable."
        )
    )
    async def ingest(
        kind: str,
        path: str | None = None,
        content_base64: str | None = None,
        filename: str | None = None,
        mine: bool = False,
    ) -> str:
        def _do() -> str:
            # Coercion and validation live in the facade
            # (arch-facade-ingest-coercion); its ValueError propagates to the
            # MCP client unchanged.
            result = facade.ingest(
                path=path,
                content_base64=content_base64,
                filename=filename,
                kind=kind,
                mine=mine,
            )
            return _json(result)

        return await anyio.to_thread.run_sync(_do)

    @server.tool(description="Frontmatter + body Markdown for one page (by kind + slug).")
    async def page_get(kind: str, slug: str) -> str:
        return await anyio.to_thread.run_sync(lambda: _json(facade.page_get(kind, slug)))

    @server.tool(description="A filtered, newest-first list of wiki pages for discovery.")
    async def page_list(
        kind: str | None = None, status: str | None = None, limit: int = 200
    ) -> str:
        return await anyio.to_thread.run_sync(
            lambda: _json(facade.page_list(kind=kind, status=status, limit=limit))
        )

    @server.tool(description="Derived-index document counts and sync-lag rows.")
    async def index_status() -> str:
        return await anyio.to_thread.run_sync(lambda: _json(facade.index_status()))

    return server


def run() -> None:
    """Run the MCP server over stdio. Imported lazily by ``compendium mcp``."""
    build_server().run()
