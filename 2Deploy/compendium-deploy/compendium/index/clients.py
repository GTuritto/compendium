"""Clients for the derived index stores: OpenSearch and Qdrant.

Both are derived caches (ADR-005), rebuildable from PostgreSQL and the vault.
Clients are constructed from config; the reachability helpers let tests skip
when a store is not running, mirroring the PostgreSQL pattern in the wiki
integration tests.
"""

from __future__ import annotations

from opensearchpy import OpenSearch
from qdrant_client import QdrantClient

from compendium.config import load_config


def opensearch_client(url: str | None = None) -> OpenSearch:
    """Open an OpenSearch client. The URL defaults to OPENSEARCH_URL from config."""
    if url is None:
        url = load_config().opensearch_url
    return OpenSearch(hosts=[url], use_ssl=url.startswith("https"), verify_certs=False)


def qdrant_client(url: str | None = None) -> QdrantClient:
    """Open a Qdrant client. The URL defaults to QDRANT_URL from config."""
    if url is None:
        url = load_config().qdrant_url
    return QdrantClient(url=url)


def opensearch_reachable(client: OpenSearch) -> bool:
    """True if the OpenSearch cluster answers a ping."""
    try:
        return bool(client.ping())
    except Exception:
        return False


def qdrant_reachable(client: QdrantClient) -> bool:
    """True if Qdrant answers a collections listing."""
    try:
        client.get_collections()
        return True
    except Exception:
        return False
