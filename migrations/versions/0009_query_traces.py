"""Migration 9: query_traces.

query_embedding is REAL[] rather than pgvector's VECTOR(n): vector search
lives in Qdrant, this column only persists the embedding for trace replay.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE query_traces (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            corpus_revision TEXT REFERENCES corpus_revisions(id),
            query_text TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            query_embedding REAL[],
            pipeline JSONB NOT NULL,
            final_ranking JSONB NOT NULL,
            latencies_ms JSONB NOT NULL,
            coverage_score DOUBLE PRECISION,
            fallback_to_chunks BOOLEAN NOT NULL DEFAULT FALSE,
            gaps JSONB NOT NULL DEFAULT '[]',
            graph_expansion JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX query_traces_corpus_idx "
        "ON query_traces (corpus_revision, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX query_traces_fallback_idx "
        "ON query_traces (fallback_to_chunks) WHERE fallback_to_chunks"
    )


def downgrade() -> None:
    op.execute("DROP TABLE query_traces")
