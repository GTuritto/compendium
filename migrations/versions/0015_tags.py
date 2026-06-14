"""Migration 15: tags on sources and wiki pages (ADR-019, v0.5).

Curator-assigned, retrieval-filter-grade labels, orthogonal to topics (ADR-006)
and aliases. PostgreSQL is the system of record; tags propagate into the
derived-index payloads for index-level filtering. Join tables (not array
columns) so rename/merge and usage counts are clean. Both link tables cascade
on their parent's delete, so a source/page hard delete (ADR-018) drops its tag
links automatically.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tags (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE source_tags (
            source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (source_id, tag_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE page_tags (
            page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (page_id, tag_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_source_tags_tag ON source_tags(tag_id)")
    op.execute("CREATE INDEX ix_page_tags_tag ON page_tags(tag_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS page_tags")
    op.execute("DROP TABLE IF EXISTS source_tags")
    op.execute("DROP TABLE IF EXISTS tags")
