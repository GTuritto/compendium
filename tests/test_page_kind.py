"""The PageKind registry is the single home for per-kind page rules; assert its
membership and that frontmatter/required-fields match the established contract."""

from __future__ import annotations

from compendium.wiki import page_kind as pk
from compendium.wiki.page import Page


def _concept() -> Page:
    return Page(kind="concept", title="Psych Safety", slug="psych-safety", body="b",
                id="11111111-1111-1111-1111-111111111111",
                topic_ids=["t1"], aliases=["ps"])


def _topic() -> Page:
    return Page(kind="topic", title="Teams", slug="teams", body="b",
                id="22222222-2222-2222-2222-222222222222", parent_topic_id="p1")


def _source() -> Page:
    return Page(kind="source", title="Paper", slug="paper", body="b",
                id="33333333-3333-3333-3333-333333333333",
                source_id="s1", source_kind="paper", inspection_status="passed",
                source_metadata={"x": 1})


def test_registry_has_the_three_kinds() -> None:
    assert set(pk.PAGE_KIND_REGISTRY) == {"concept", "topic", "source"}
    assert pk.PAGE_KIND_NAMES == ("concept", "topic", "source")


def test_required_fields_match_the_contract() -> None:
    assert pk.REQUIRED_BY_KIND == {
        "concept": ("topic_ids",),
        "topic": ("parent_topic_id",),
        "source": ("source_id", "source_kind", "source_metadata", "inspection_status"),
    }


def test_subdirs() -> None:
    assert pk.PAGE_KIND_REGISTRY["concept"].subdir == "concepts"
    assert pk.PAGE_KIND_REGISTRY["topic"].subdir == "topics"
    assert pk.PAGE_KIND_REGISTRY["source"].subdir == "sources"


def test_frontmatter_fields_keys_and_order() -> None:
    assert list(pk.PAGE_KIND_REGISTRY["concept"].frontmatter_fields(_concept())) == ["topic_ids", "aliases"]
    assert list(pk.PAGE_KIND_REGISTRY["topic"].frontmatter_fields(_topic())) == ["parent_topic_id"]
    assert list(pk.PAGE_KIND_REGISTRY["source"].frontmatter_fields(_source())) == [
        "source_id", "source_kind", "source_metadata", "inspection_status"]


def test_source_frontmatter_defaults_metadata_to_empty_dict() -> None:
    p = _source()
    p.source_metadata = None
    assert pk.PAGE_KIND_REGISTRY["source"].frontmatter_fields(p)["source_metadata"] == {}


def test_db_fields_are_kind_gated() -> None:
    c = pk.PAGE_KIND_REGISTRY["concept"].db_fields(_concept())
    assert c["aliases"] == ["ps"] and c["source_id"] is None and c["parent_topic_id"] is None
    s = pk.PAGE_KIND_REGISTRY["source"].db_fields(_source())
    assert s["source_id"] == "s1" and s["aliases"] == [] and s["source_kind"] == "paper"
    t = pk.PAGE_KIND_REGISTRY["topic"].db_fields(_topic())
    assert t["parent_topic_id"] == "p1" and t["source_id"] is None


def test_writes_topic_links_only_for_concept() -> None:
    assert pk.PAGE_KIND_REGISTRY["concept"].writes_topic_links is True
    assert pk.PAGE_KIND_REGISTRY["topic"].writes_topic_links is False
    assert pk.PAGE_KIND_REGISTRY["source"].writes_topic_links is False


def test_source_lint_page_flags_missing_fields() -> None:
    issues: list[tuple[str, str, str]] = []
    p = _source()
    p.source_id = None
    pk.PAGE_KIND_REGISTRY["source"].lint_page(p, lambda r, s, m: issues.append((r, s, m)))
    assert any(r == "kind-specific-fields" for r, _, _ in issues)
