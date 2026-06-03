"""Migration 4: chunks.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            parent_section TEXT,
            body TEXT NOT NULL,
            body_hash TEXT NOT NULL,
            token_count INTEGER,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_id, body_hash)
        )
        """
    )
    op.execute("CREATE INDEX chunks_source_pos_idx ON chunks (source_id, position)")


def downgrade() -> None:
    op.execute("DROP TABLE chunks")
