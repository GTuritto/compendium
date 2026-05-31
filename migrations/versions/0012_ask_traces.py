"""Migration 12: ask_traces.

The companion trace for composed answers (v0.2 Phase 6). One row per
``compendium ask`` invocation, joined to the ``query_traces`` row produced by
the retrieval via ``query_trace_id``. A refusal still writes a row
(``refused=true``, ``answer_text`` null). ``cost_estimate`` is a best-effort
figure from token counts and a static per-model rate table, not billing-grade.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ask_traces (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            query_trace_id UUID NOT NULL REFERENCES query_traces(id),
            prompt_template_id TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_estimate DOUBLE PRECISION,
            answer_text TEXT,
            refused BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ask_traces_query_trace_idx "
        "ON ask_traces (query_trace_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ask_traces")
