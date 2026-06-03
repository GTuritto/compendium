"""Migration 6: wiki_page_revisions and the deferred current_revision_id FK.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE wiki_page_revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            frontmatter JSONB NOT NULL,
            generator page_generator NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX wiki_page_revisions_page_idx "
        "ON wiki_page_revisions (page_id, created_at DESC)"
    )
    # Resolve the circular reference now that both tables exist.
    op.execute(
        """
        ALTER TABLE wiki_pages
            ADD CONSTRAINT wiki_pages_current_revision_fk
            FOREIGN KEY (current_revision_id)
            REFERENCES wiki_page_revisions(id)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE wiki_pages DROP CONSTRAINT wiki_pages_current_revision_fk"
    )
    op.execute("DROP TABLE wiki_page_revisions")
