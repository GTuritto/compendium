"""HTTP transport for the access surface (``compendium serve``, v0.2 Phase 7).

A FastAPI app over the shared :mod:`compendium.api.facade`, bound to
``127.0.0.1`` with no auth (colocated callers only, ADR-011). Route handlers are
plain ``def`` so FastAPI runs the blocking facade calls in its threadpool. The
six verbs map to: ``POST /query``, ``POST /ask`` (buffered) + ``POST
/ask/stream`` (chunked), ``POST /ingest`` (path or base64 bytes), ``GET
/page_get``, ``GET /page_list``, ``GET /index_status``. Responses serialize via
the shared :func:`compendium.api.serialize.to_payload`, so the HTTP contract is
byte-for-byte the CLI's ``--format json``.

Network exposure, auth, and TLS are deferred to v0.3+ (ADR-011); ``--host`` may
bind a non-loopback interface but doing so is unsafe until then.
"""

from __future__ import annotations

import base64
import json
from typing import Any


def create_app() -> Any:
    """Build the FastAPI app over the facade. Imported lazily by ``serve``."""
    from fastapi import Body, FastAPI, HTTPException, Query
    from fastapi.responses import StreamingResponse

    from compendium import __version__
    from compendium.api import facade, to_payload

    app = FastAPI(title="Compendium access surface", version=__version__)

    @app.middleware("http")
    async def _refresh_behavior_config(request: Any, call_next: Any) -> Any:
        # The serve unit is long-running; drop the cached behavior config at the
        # start of each request so a config/settings.yaml change is picked up
        # without a restart (arch-config-cache-seam). Storage-URL/secret reads are
        # uncached anyway. Re-parse cost is negligible at personal request volume.
        from compendium.config import invalidate_config_cache

        invalidate_config_cache()
        return await call_next(request)

    @app.post("/query")
    def http_query(payload: dict = Body(...)) -> Any:
        text = (payload or {}).get("text")
        if not text:
            raise HTTPException(status_code=400, detail="missing 'text'")
        return to_payload(facade.query(text))

    @app.post("/ask")
    def http_ask(payload: dict = Body(...)) -> Any:
        question = (payload or {}).get("question")
        if not question:
            raise HTTPException(status_code=400, detail="missing 'question'")
        return to_payload(facade.ask(question))

    @app.post("/ask/stream")
    def http_ask_stream(payload: dict = Body(...)) -> Any:
        question = (payload or {}).get("question")
        if not question:
            raise HTTPException(status_code=400, detail="missing 'question'")
        return StreamingResponse(
            _ask_token_stream(facade, to_payload, question),
            media_type="text/plain",
        )

    @app.post("/ingest")
    def http_ingest(payload: dict = Body(...)) -> Any:
        payload = payload or {}
        kind = payload.get("kind")
        if not kind:
            raise HTTPException(status_code=400, detail="missing 'kind'")
        path = payload.get("path")
        content_b64 = payload.get("content_base64")
        if content_b64 is not None:
            try:
                content = base64.b64decode(content_b64)
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=400, detail=f"invalid content_base64: {exc}"
                ) from exc
            result = facade.ingest(
                content=content,
                filename=payload.get("filename"),
                kind=kind,
                mine=bool(payload.get("mine", False)),
            )
        elif path is not None:
            result = facade.ingest(path=path, kind=kind, mine=bool(payload.get("mine", False)))
        else:
            raise HTTPException(
                status_code=400, detail="ingest requires 'path' or 'content_base64'"
            )
        return to_payload(result)

    @app.get("/page_get")
    def http_page_get(kind: str = Query(...), slug: str = Query(...)) -> Any:
        page = facade.page_get(kind, slug)
        if page is None:
            raise HTTPException(status_code=404, detail="page not found")
        return page

    @app.get("/page_list")
    def http_page_list(
        kind: str | None = Query(None),
        status: str | None = Query(None),
        limit: int = Query(200),
    ) -> Any:
        return to_payload(facade.page_list(kind=kind, status=status, limit=limit))

    @app.get("/index_status")
    def http_index_status() -> Any:
        return to_payload(facade.index_status())

    return app


def _ask_token_stream(facade: Any, to_payload: Any, question: str):
    """Bridge the facade's sync ``on_token`` callback to a chunked HTTP stream.

    Runs ``facade.ask`` in a worker thread; yields answer deltas as they arrive,
    then a final newline-prefixed JSON object carrying citations, coverage, and
    the trace ids. A refusal yields no answer deltas, only the final object.
    """
    import queue
    import threading

    q: queue.Queue = queue.Queue()
    box: dict = {}

    def on_token(token: str) -> None:
        q.put(("tok", token))

    def run() -> None:
        try:
            box["result"] = facade.ask(question, on_token=on_token)
            q.put(("done", None))
        except Exception as exc:  # surfaced to the client as a final error line
            box["error"] = str(exc)
            q.put(("err", None))

    threading.Thread(target=run, daemon=True).start()

    while True:
        kind, value = q.get()
        if kind == "tok":
            yield value
        elif kind == "err":
            yield "\n" + json.dumps({"error": box.get("error", "ask failed")})
            return
        else:
            yield "\n" + json.dumps(to_payload(box["result"]))
            return


def run(*, host: str = "127.0.0.1", port: int = 8787) -> None:
    """Run the HTTP server with uvicorn. Imported lazily by ``compendium serve``."""
    import uvicorn

    from compendium.profiling import install_memory_signal_handlers

    # Leak hunting on the long-running daemon (opt-in, in-process): SIGUSR1
    # arms a tracemalloc baseline, SIGUSR2 writes a diff report into the
    # profile artifacts dir. Must happen here, in the main thread, before
    # uvicorn installs its own SIGTERM/SIGINT handling.
    install_memory_signal_handlers()

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
