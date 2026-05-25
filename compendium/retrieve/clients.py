"""Async clients for the search fan-out.

Phase 5 queries OpenSearch and Qdrant in parallel (ADR-003 step 3). The
fan-out is async (``asyncio.gather``) while the PostgreSQL layer stays
synchronous ``psycopg 3`` (CLAUDE.md). These are the *read* clients; Phase 4's
synchronous ``compendium/index/clients.py`` keeps owning indexing and reindex.
Both client families read the same Phase 4 index/collection names and mappings.
"""

from __future__ import annotations

from opensearchpy import AsyncOpenSearch
from qdrant_client import AsyncQdrantClient

from compendium.config import load_config


def async_opensearch_client(url: str | None = None) -> AsyncOpenSearch:
    """Open an async OpenSearch client. URL defaults to OPENSEARCH_URL from config."""
    if url is None:
        url = load_config().opensearch_url
    return AsyncOpenSearch(
        hosts=[url], use_ssl=url.startswith("https"), verify_certs=False
    )


def async_qdrant_client(url: str | None = None) -> AsyncQdrantClient:
    """Open an async Qdrant client. URL defaults to QDRANT_URL from config."""
    if url is None:
        url = load_config().qdrant_url
    return AsyncQdrantClient(url=url)


async def opensearch_reachable(client: AsyncOpenSearch) -> bool:
    """True if the OpenSearch cluster answers a ping."""
    try:
        return bool(await client.ping())
    except Exception:
        return False


async def qdrant_reachable(client: AsyncQdrantClient) -> bool:
    """True if Qdrant answers a collections listing."""
    try:
        await client.get_collections()
        return True
    except Exception:
        return False
