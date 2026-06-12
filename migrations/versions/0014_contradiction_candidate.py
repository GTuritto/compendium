"""Migration 14: the contradiction_candidate signal kind (ADR-014, v0.3 Phase 1).

A *proposed* contradiction (LLM-suggested, awaiting curator approval) is a
distinct kind from a curator-noticed ``unresolved_contradiction`` — provenance
clarity is the point of the suggestion shape.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE curation_signal_kind ADD VALUE IF NOT EXISTS 'contradiction_candidate'"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value in place; rows of this kind would
    # also dangle. Like the enum-altering migrations before it, this is a
    # forward-only change — downgrade is a documented no-op.
    pass
