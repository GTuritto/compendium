"""Migration 16: agent_objects — verbatim agent storage (ADR-017, v0.5).

A PostgreSQL-backed key-value store an agent writes to and reads back
byte-for-byte. NOT the wiki and NOT a derived index: it is never synced into
OpenSearch/Qdrant/Memgraph until an object is promoted (which runs it through
the normal ingest pipeline to become a source page). Upsert is last-write-wins
on (collection, key).

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_objects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collection TEXT NOT NULL DEFAULT 'default',
            key TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'text/plain',
            body BYTEA NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (collection, key)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_objects")
