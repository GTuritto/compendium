"""The single source of per-type edge rules for the Memgraph graph.

Each of the seven edge types (three structural, four semantic) is one
:class:`EdgeType` record carrying every rule a caller might branch on: is it
structural (``automatic``), ``symmetric`` (one edge per unordered pair),
``walkable`` by fast-loop expansion, ``extractable`` by the LLM (ADR-010), and
``curator_settable`` via ``graph link`` (ADR-009). The derived tuples below are
computed once from the registry, so the rule for a type lives in exactly one
place: ``schema.py``, ``browse.py``, ``extract.py``, and the CLI all consult
this module rather than restating a literal.

Membership mirrors the established behaviour exactly:
  extractable      = {RELATED_TO, PREREQUISITE_FOR}              (ADR-010)
  walkable         = {RELATED_TO, PREREQUISITE_FOR, SYNTHESIZES} (the old _SEMANTIC_RELS)
  symmetric        = {RELATED_TO}
  curator_settable = the four semantic types
  automatic        = {PART_OF, EVIDENCES, GROUNDS}
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeType:
    """One Memgraph edge type and the rules that govern it."""

    name: str
    automatic: bool = False        # structural, written by projection (PART_OF/EVIDENCES/GROUNDS)
    symmetric: bool = False        # one edge per unordered pair (endpoints canonicalised)
    walkable: bool = False         # traversed by fast-loop expansion
    extractable: bool = False      # the LLM extractor may write it (ADR-010)
    curator_settable: bool = False  # a curator may write it via `graph link` (ADR-009)


# Registry, in the canonical order (structural first, then semantic) so the
# derived tuples below match the orders the codebase used before consolidation.
REGISTRY: tuple[EdgeType, ...] = (
    EdgeType("PART_OF", automatic=True),
    EdgeType("EVIDENCES", automatic=True),
    EdgeType("GROUNDS", automatic=True),
    EdgeType("RELATED_TO", symmetric=True, walkable=True, extractable=True, curator_settable=True),
    EdgeType("PREREQUISITE_FOR", walkable=True, extractable=True, curator_settable=True),
    EdgeType("SYNTHESIZES", walkable=True, curator_settable=True),
    EdgeType("CONTRADICTS", curator_settable=True),
)

BY_NAME: dict[str, EdgeType] = {e.name: e for e in REGISTRY}

# Derived tuples — the single source the rest of the codebase imports.
EDGE_TYPES: tuple[str, ...] = tuple(e.name for e in REGISTRY)
AUTOMATIC_EDGES: tuple[str, ...] = tuple(e.name for e in REGISTRY if e.automatic)
SEMANTIC_EDGES: tuple[str, ...] = tuple(e.name for e in REGISTRY if not e.automatic)
EXTRACTABLE_EDGES: tuple[str, ...] = tuple(e.name for e in REGISTRY if e.extractable)
WALKABLE_EDGES: tuple[str, ...] = tuple(e.name for e in REGISTRY if e.walkable)
CURATOR_SETTABLE_EDGES: tuple[str, ...] = tuple(e.name for e in REGISTRY if e.curator_settable)


def is_semantic(edge_type: str) -> bool:
    """True for a semantic edge type, False for a structural one. Raises on unknown."""
    return not BY_NAME[edge_type].automatic


def is_symmetric(edge_type: str) -> bool:
    """True if the edge is symmetric (endpoints should be canonicalised)."""
    return BY_NAME[edge_type].symmetric


def walkable_rel_pattern() -> str:
    """The Cypher relationship alternation for fast-loop expansion, e.g.
    ``RELATED_TO|PREREQUISITE_FOR|SYNTHESIZES``."""
    return "|".join(WALKABLE_EDGES)
