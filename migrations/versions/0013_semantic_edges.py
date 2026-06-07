"""Migration 13: semantic_edges.

The system-of-record home for semantic graph edges (RELATED_TO,
PREREQUISITE_FOR, SYNTHESIZES, CONTRADICTS). Before this, semantic edges lived
only in Memgraph -- a derived store ``compendium graph rebuild`` drops and
re-derives -- so a rebuild silently and permanently wiped every curator,
SYNTHESIZES, and LLM-extracted edge (structural edges survived because they are
re-derived from PostgreSQL + the vault; semantic edges had no such home).

Persisting them here (with the ADR-010 provenance bag) lets the rebuild replay
them, keeping Memgraph fully derived and the rebuild deterministic
(ADR-004 / ADR-005). One row per directed edge, keyed on the same tuple
Memgraph ``MERGE``s on. ``source_revision_id`` is TEXT, not UUID, so it mirrors
the graph property verbatim (the LLM extractor stores ``""`` when a page has no
current revision; curator/lifecycle writes omit it).

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE semantic_edges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            edge_type TEXT NOT NULL,
            from_label TEXT NOT NULL,
            from_id TEXT NOT NULL,
            to_label TEXT NOT NULL,
            to_id TEXT NOT NULL,
            extracted_by TEXT NOT NULL,
            model TEXT,
            confidence DOUBLE PRECISION,
            extracted_at TEXT,
            source_revision_id TEXT,
            weight DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (edge_type, from_label, from_id, to_label, to_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE semantic_edges")
