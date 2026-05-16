"""Migration 2: sources and source_documents.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind source_kind NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            year INTEGER,
            url TEXT,
            identifier TEXT,
            metadata JSONB NOT NULL DEFAULT '{}',
            inspection_status inspection_status,
            inspection_notes TEXT,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            content_hash TEXT NOT NULL,
            UNIQUE (kind, content_hash)
        )
        """
    )
    op.execute(
        "CREATE INDEX sources_title_idx ON sources "
        "USING GIN (to_tsvector('simple', title))"
    )
    op.execute(
        """
        CREATE TABLE source_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            byte_size BIGINT NOT NULL,
            added_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE source_documents")
    op.execute("DROP TABLE sources")
