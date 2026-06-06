"""The SignalGenerator registry is the single home for the slow loop's
generators; assert its membership/declarations and that Signal stays
tuple-compatible."""

from __future__ import annotations

from compendium.curate import signals as sg
from compendium.curate.signal_generator import Signal


def test_registry_has_the_four_signal_generators() -> None:
    names = [g.name for g in sg.REGISTRY]
    assert names == ["low_coverage", "thin_grounding", "dangling", "contradictions"]
    assert len(sg.REGISTRY) == 4


def test_each_generator_declares_kinds_and_required_stores() -> None:
    by_name = {g.name: g for g in sg.REGISTRY}
    assert by_name["low_coverage"].kinds == ("low_coverage_query",)
    assert by_name["low_coverage"].requires == ("postgres",)
    assert by_name["thin_grounding"].kinds == ("thin_grounding",)
    assert by_name["thin_grounding"].requires == ("graph",)
    assert by_name["dangling"].kinds == ("dangling_concept",)
    assert by_name["dangling"].requires == ("graph",)
    assert by_name["contradictions"].kinds == ("unresolved_contradiction",)
    assert by_name["contradictions"].requires == ("graph",)


def test_graph_generators_require_graph_postgres_generator_requires_postgres() -> None:
    graph = {g.name for g in sg.REGISTRY if g.requires == ("graph",)}
    assert graph == {"thin_grounding", "dangling", "contradictions"}
    postgres = {g.name for g in sg.REGISTRY if g.requires == ("postgres",)}
    assert postgres == {"low_coverage"}


def test_skipped_kinds_derive_from_the_registry_not_a_literal() -> None:
    # The runner derives the graph skip-list from the graph generators' kinds.
    graph_kinds = tuple(k for g in sg.REGISTRY if g.requires == ("graph",) for k in g.kinds)
    assert set(graph_kinds) == {"thin_grounding", "dangling_concept", "unresolved_contradiction"}


def test_signal_is_named_but_unpacks_as_a_plain_tuple() -> None:
    s = Signal("low_coverage_query", 7, {"query_text": "x"})
    kind, priority, payload = s  # unpacks like the old 3-tuple
    assert (kind, priority, payload) == ("low_coverage_query", 7, {"query_text": "x"})
    assert s == ("low_coverage_query", 7, {"query_text": "x"})  # equal to plain tuple
    assert s.kind == "low_coverage_query" and s.priority == 7  # but named


def test_extractor_is_not_a_signal_generator() -> None:
    # ADR-010 extraction is a separate workflow; it must not appear in the registry.
    assert "extracted_edges" not in {g.name for g in sg.REGISTRY}
    assert all("extract" not in g.name for g in sg.REGISTRY)
