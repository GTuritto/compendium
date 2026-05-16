"""Migration 8: promotion_events.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE promotion_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            kind promotion_kind NOT NULL,
            from_revision_id UUID REFERENCES wiki_page_revisions(id),
            to_revision_id UUID REFERENCES wiki_page_revisions(id),
            related_page_ids UUID[] NOT NULL DEFAULT '{}',
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE promotion_events")
