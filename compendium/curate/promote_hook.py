"""Closing the curation loop on promotion (ADR-009, Phase 9).

When a page synthesized from a signal is promoted, mark the signal `addressed`
with the promoted revision and add `SYNTHESIZES` edges from the new concept to
the sources its grounding chunks came from. Called inside the promote
transaction; a no-op for ordinary (non-curation) promotions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from compendium.db import repository
from compendium.graph import projection, schema
from compendium.graph.client import graph_driver, graph_reachable
from compendium.wiki.page import parse_markdown


def address_on_promote(
    conn: psycopg.Connection,
    page: dict[str, Any],
    to_revision_id: str,
    vault_path: str,
) -> str | None:
    """If this page addresses an in-progress signal, close it and add edges.

    Returns the addressed signal id, or None when the promotion is unrelated to
    a curation signal.
    """
    signal = repository.find_in_progress_signal_by_synth_slug(conn, page["slug"])
    if signal is None:
        return None

    repository.set_signal_status(
        conn, signal["id"], "addressed", addressed_revision_id=to_revision_id
    )

    # SYNTHESIZES: concept -> each source its grounding chunks came from.
    if page["kind"] == "concept":
        path = Path(vault_path) / page["file_path"]
        if path.is_file():
            body = parse_markdown(path.read_text(encoding="utf-8")).body
            chunk_ids = projection.parse_grounding_chunk_ids(body)
            source_ids = repository.source_ids_for_chunks(conn, chunk_ids)
            if source_ids:
                driver = graph_driver()
                try:
                    if graph_reachable(driver):
                        for source_id in source_ids:
                            schema.upsert_edge(
                                driver, "SYNTHESIZES",
                                "Concept", str(page["id"]), "Source", source_id,
                            )
                finally:
                    driver.close()
    return str(signal["id"])
