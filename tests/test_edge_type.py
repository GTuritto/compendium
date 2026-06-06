"""The EdgeType registry is the single source of per-type edge rules; assert its
derived tuples equal the known-good membership (the behaviour the scattered
literals encoded before consolidation)."""

from __future__ import annotations

from compendium.graph import edge_type as et


def test_registry_covers_exactly_the_seven_types() -> None:
    assert set(et.EDGE_TYPES) == {
        "PART_OF", "EVIDENCES", "GROUNDS",
        "RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS",
    }
    assert len(et.REGISTRY) == 7


def test_automatic_and_semantic_partition() -> None:
    assert et.AUTOMATIC_EDGES == ("PART_OF", "EVIDENCES", "GROUNDS")
    assert et.SEMANTIC_EDGES == ("RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS")
    assert set(et.AUTOMATIC_EDGES).isdisjoint(et.SEMANTIC_EDGES)


def test_extractable_set_matches_adr_010() -> None:
    assert et.EXTRACTABLE_EDGES == ("RELATED_TO", "PREREQUISITE_FOR")


def test_walkable_set_matches_old_semantic_rels() -> None:
    assert et.WALKABLE_EDGES == ("RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES")
    assert et.walkable_rel_pattern() == "RELATED_TO|PREREQUISITE_FOR|SYNTHESIZES"
    assert "CONTRADICTS" not in et.WALKABLE_EDGES


def test_symmetric_is_related_to_only() -> None:
    assert et.is_symmetric("RELATED_TO") is True
    for name in ("PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS"):
        assert et.is_symmetric(name) is False


def test_curator_settable_is_the_four_semantic_types() -> None:
    assert et.CURATOR_SETTABLE_EDGES == ("RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS")


def test_is_semantic_classifies_structural_vs_semantic() -> None:
    assert et.is_semantic("RELATED_TO") is True
    assert et.is_semantic("PART_OF") is False


def test_edge_types_order_is_structural_then_semantic() -> None:
    # EDGE_TYPES preserves the historical AUTOMATIC_EDGES + SEMANTIC_EDGES order
    # (it is the Cypher label whitelist; order is part of the contract).
    assert et.EDGE_TYPES == et.AUTOMATIC_EDGES + et.SEMANTIC_EDGES
