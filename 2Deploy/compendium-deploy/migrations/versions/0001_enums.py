"""Migration 1: enum types.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# name -> ordered enum values, per docs/Compendium.md Part III.
_ENUMS: dict[str, tuple[str, ...]] = {
    "source_kind": ("book", "article", "paper", "note", "web"),
    "page_kind": ("concept", "topic", "source"),
    "page_status": ("draft", "canonical", "deprecated"),
    "page_generator": ("human", "synth", "repair"),
    "inspection_status": ("passed", "passed_with_warnings", "failed"),
    "index_kind": (
        "opensearch_pages",
        "opensearch_chunks",
        "qdrant_pages",
        "qdrant_chunks",
        "memgraph",
    ),
    "sync_state": ("pending", "indexed", "failed"),
    "promotion_kind": (
        "draft_to_canonical",
        "canonical_to_deprecated",
        "merge",
        "split",
    ),
    "curation_signal_kind": (
        "gap",
        "thin_grounding",
        "unresolved_contradiction",
        "dangling_concept",
        "low_coverage_query",
    ),
    "curation_signal_status": ("open", "in_progress", "addressed", "dropped"),
}


def upgrade() -> None:
    for name, values in _ENUMS.items():
        labels = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")


def downgrade() -> None:
    for name in reversed(list(_ENUMS)):
        op.execute(f"DROP TYPE {name}")
