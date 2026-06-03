"""Migration 5: wiki_pages and wiki_pages_topics.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # current_revision_id has no FK yet; wiki_page_revisions does not exist
    # until migration 0006, which adds the constraint.
    op.execute(
        """
        CREATE TABLE wiki_pages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind page_kind NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            status page_status NOT NULL DEFAULT 'draft',
            content_hash TEXT NOT NULL,
            current_revision_id UUID,
            corpus_revision TEXT REFERENCES corpus_revisions(id),
            parent_topic_id UUID REFERENCES wiki_pages(id),
            source_id UUID REFERENCES sources(id),
            source_kind source_kind,
            source_metadata JSONB,
            inspection_status inspection_status,
            aliases TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (kind, slug)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE wiki_pages_topics (
            page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            topic_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            PRIMARY KEY (page_id, topic_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE wiki_pages_topics")
    op.execute("DROP TABLE wiki_pages")
