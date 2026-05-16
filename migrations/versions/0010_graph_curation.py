"""Migration 10: graph_curation_signals and graph_analysis_runs.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # run_id has no FK yet; graph_analysis_runs does not exist until below.
    op.execute(
        """
        CREATE TABLE graph_curation_signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind curation_signal_kind NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            payload JSONB NOT NULL,
            status curation_signal_status NOT NULL DEFAULT 'open',
            addressed_revision_id UUID REFERENCES wiki_page_revisions(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            addressed_at TIMESTAMPTZ,
            run_id UUID
        )
        """
    )
    op.execute(
        """
        CREATE TABLE graph_analysis_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            signal_count INTEGER NOT NULL DEFAULT 0,
            summary JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE graph_curation_signals
            ADD CONSTRAINT graph_curation_signals_run_fk
            FOREIGN KEY (run_id) REFERENCES graph_analysis_runs(id)
        """
    )
    op.execute(
        "CREATE INDEX curation_signals_open_idx "
        "ON graph_curation_signals (status, priority DESC) WHERE status = 'open'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE graph_curation_signals "
        "DROP CONSTRAINT graph_curation_signals_run_fk"
    )
    op.execute("DROP TABLE graph_analysis_runs")
    op.execute("DROP TABLE graph_curation_signals")
