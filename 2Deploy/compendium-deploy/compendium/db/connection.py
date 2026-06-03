"""Synchronous PostgreSQL connections via psycopg 3."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from compendium.config import load_config


def connect(url: str | None = None) -> psycopg.Connection:
    """Open a psycopg connection. The URL defaults to POSTGRES_URL from config.

    Rows are returned as dicts.
    """
    if url is None:
        url = load_config().postgres_url
    return psycopg.connect(url, row_factory=dict_row)


@contextmanager
def connection(url: str | None = None) -> Iterator[psycopg.Connection]:
    """A connection that commits on clean exit, rolls back on error, always closes."""
    conn = connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
