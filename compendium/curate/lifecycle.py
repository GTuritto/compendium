"""The curation-signal lifecycle (ADR-009, Phase 9; review #2 candidate 3).

One owner for a signal's state machine and the transitions that drive it:

    open ──begin──▶ in_progress ──address_on_promote──▶ addressed

``begin`` runs when a draft is synthesized from a signal; ``address_on_promote``
runs inside the promote transaction when that draft is promoted, marking the
signal ``addressed`` and adding the ``SYNTHESIZES`` edges. Both transitions are
curator-triggered (ADR-009: no autonomous promotion) — this module owns *where*
the state moves, not *whether*. The previous split (status flips in
``curate/synth.py`` plus a separate ``curate/promote_hook.py`` reached by an
inline import in ``trace/promote.py``) is consolidated here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from compendium.db import repository
from compendium.graph import projection, schema
from compendium.graph.client import graph_connection, graph_reachable
from compendium.wiki.page import parse_markdown


def begin(
    conn: psycopg.Connection,
    signal_id: str,
    *,
    synth_page_id: str,
    synth_slug: str,
) -> None:
    """``open`` → ``in_progress``: a draft was synthesized from the signal.

    Tags the signal with the page it produced so a later promotion of that page
    can find and address it (see :func:`address_on_promote`).
    """
    repository.set_signal_status(conn, signal_id, "in_progress")
    repository.attach_synth_page(conn, signal_id, synth_page_id, synth_slug)


def address_on_promote(
    conn: psycopg.Connection,
    page: dict[str, Any],
    to_revision_id: str,
    vault_path: str,
) -> str | None:
    """``in_progress`` → ``addressed``: the synthesized page was promoted.

    Closes the signal against the promoted revision and adds ``SYNTHESIZES``
    edges from the new concept to the sources its grounding chunks came from.
    Returns the addressed signal id, or ``None`` when the promotion is unrelated
    to a curation signal. Called inside the promote transaction.
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
                with graph_connection() as driver:
                    if graph_reachable(driver):
                        for source_id in source_ids:
                            # SYNTHESIZES is lifecycle-owned; route through the
                            # semantic-edge seam with curator-class provenance so
                            # an LLM extraction can never overwrite it.
                            schema.upsert_semantic_edge(
                                driver, "SYNTHESIZES",
                                "Concept", str(page["id"]), "Source", source_id,
                                provenance={"extracted_by": "curator"},
                            )
    return str(signal["id"])
