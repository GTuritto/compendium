"""The callable access surface (ADR-011, v0.2 Phase 7).

A shared facade (:mod:`compendium.api.facade`) and two thin transports —
``compendium serve`` (HTTP, :mod:`compendium.api.http`) and ``compendium mcp``
(MCP stdio, :mod:`compendium.api.mcp`) — expose six verbs to colocated callers.
"""

from __future__ import annotations

from compendium.api.facade import (
    VERBS,
    ask,
    index_status,
    ingest,
    page_get,
    page_list,
    query,
)
from compendium.api.serialize import to_payload

__all__ = [
    "VERBS",
    "ask",
    "index_status",
    "ingest",
    "page_get",
    "page_list",
    "query",
    "to_payload",
]
