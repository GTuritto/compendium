"""Deterministic seeding for the golden dataset (Phase 10).

Builds a fixed corpus state with the stub embedder/synth: ingest the markdown
fixture (source page + chunks), synthesize the `psychological-safety` concept,
populate the indexes, and rebuild the graph. Callers set the stub env and point
POSTGRES_URL/VAULT_PATH at a dedicated golden database/vault first.
"""

from __future__ import annotations

from pathlib import Path

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def seed_corpus(vault_path: str) -> None:
    """Ingest the fixture, synth the expected concept, reindex, rebuild the graph."""
    from compendium.db.connection import connection
    from compendium.graph.rebuild import rebuild
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest
    from compendium.wiki.synth import synthesize_concept

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    with connection() as conn:
        synthesize_concept(conn, "psychological safety", aliases=[], vault_path=vault_path)
    reindex("all")
    rebuild()
