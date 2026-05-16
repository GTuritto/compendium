"""Migration 11: read-only operational views for the TUI.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW v_sync_lag AS
            SELECT index_kind, state, COUNT(*) AS n
            FROM index_sync_state
            GROUP BY index_kind, state
        """
    )
    op.execute(
        """
        CREATE VIEW v_failed_sources AS
            SELECT id, title, inspection_status, inspection_notes
            FROM sources
            WHERE inspection_status = 'failed'
        """
    )
    op.execute(
        """
        CREATE VIEW v_recent_traces AS
            SELECT id, query_text, coverage_score, fallback_to_chunks, created_at
            FROM query_traces
            ORDER BY created_at DESC
            LIMIT 100
        """
    )
    op.execute(
        """
        CREATE VIEW v_open_curation_signals AS
            SELECT kind, priority, payload, created_at
            FROM graph_curation_signals
            WHERE status = 'open'
            ORDER BY priority DESC, created_at ASC
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW v_open_curation_signals")
    op.execute("DROP VIEW v_recent_traces")
    op.execute("DROP VIEW v_failed_sources")
    op.execute("DROP VIEW v_sync_lag")
