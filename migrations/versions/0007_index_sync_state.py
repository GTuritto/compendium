"""Migration 7: index_sync_state.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE index_sync_state (
            id BIGSERIAL PRIMARY KEY,
            entity_kind TEXT NOT NULL,
            entity_id UUID NOT NULL,
            index_kind index_kind NOT NULL,
            state sync_state NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (entity_kind, entity_id, index_kind)
        )
        """
    )
    op.execute(
        "CREATE INDEX index_sync_pending_idx ON index_sync_state (state) "
        "WHERE state = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE index_sync_state")
