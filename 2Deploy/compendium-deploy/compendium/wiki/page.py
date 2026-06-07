"""The wiki page model: canonical Markdown with YAML frontmatter.

A :class:`Page` is the in-memory form of a vault page. It round-trips to and
from the canonical Markdown format defined by the ``docs/Compendium.md``
frontmatter contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import yaml

from compendium.wiki import page_kind as _pk

# Per-kind rules (required fields, frontmatter shape, DB fields, subdir, lint)
# live in compendium/wiki/page_kind.py; these names derive from that registry.
PAGE_KINDS = _pk.PAGE_KIND_NAMES
PAGE_STATUSES = ("draft", "canonical", "deprecated")
GENERATORS = ("human", "synth", "repair")

# Frontmatter fields required for every page kind.
REQUIRED_ALL = (
    "id",
    "kind",
    "title",
    "slug",
    "created_at",
    "updated_at",
    "content_hash",
    "status",
    "generator",
    "corpus_revision",
)

# Additional fields required per kind (derived from the PageKind registry).
REQUIRED_BY_KIND: dict[str, tuple[str, ...]] = _pk.REQUIRED_BY_KIND


def content_hash(body: str) -> str:
    """SHA-256 over the normalized page body.

    Normalization: line endings to ``\\n``, trailing whitespace stripped
    per line, surrounding blank lines removed. Frontmatter is not included.
    """
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _as_iso(value: Any) -> str:
    """Normalize a timestamp (string or datetime) to an ISO-8601 string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@dataclass
class Page:
    """A wiki page: frontmatter fields plus the Markdown body."""

    kind: str
    title: str
    slug: str
    body: str
    id: str = ""
    status: str = "draft"
    generator: str = "synth"
    corpus_revision: str = ""
    created_at: str = ""
    updated_at: str = ""
    content_hash: str = ""
    # concept
    topic_ids: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    # topic
    parent_topic_id: str | None = None
    # source
    source_id: str | None = None
    source_kind: str | None = None
    source_metadata: dict[str, Any] | None = None
    inspection_status: str | None = None

    def frontmatter(self) -> dict[str, Any]:
        """The frontmatter dict for this page's kind, in contract order."""
        data: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "slug": self.slug,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "content_hash": self.content_hash,
            "status": self.status,
            "generator": self.generator,
            "corpus_revision": self.corpus_revision,
        }
        kind = _pk.PAGE_KIND_REGISTRY.get(self.kind)
        if kind is not None:
            data.update(kind.frontmatter_fields(self))
        return data

    def to_markdown(self) -> str:
        """Render the page as canonical Markdown (frontmatter block + body)."""
        block = yaml.safe_dump(
            self.frontmatter(), sort_keys=False, allow_unicode=True
        ).rstrip()
        return f"---\n{block}\n---\n\n{self.body.strip()}\n"


def parse_markdown(text: str) -> Page:
    """Parse canonical Markdown into a :class:`Page`."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("page is missing a frontmatter block")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("page frontmatter block is not closed")
    frontmatter = yaml.safe_load(text[4:end]) or {}
    body = text[end + len("\n---\n") :].strip("\n")
    return _from_frontmatter(frontmatter, body)


def _from_frontmatter(fm: dict[str, Any], body: str) -> Page:
    parent = fm.get("parent_topic_id")
    source_id = fm.get("source_id")
    return Page(
        kind=str(fm.get("kind", "")),
        title=str(fm.get("title", "")),
        slug=str(fm.get("slug", "")),
        body=body,
        id=str(fm.get("id", "")),
        status=str(fm.get("status", "draft")),
        generator=str(fm.get("generator", "synth")),
        corpus_revision=str(fm.get("corpus_revision", "")),
        created_at=_as_iso(fm.get("created_at")),
        updated_at=_as_iso(fm.get("updated_at")),
        content_hash=str(fm.get("content_hash", "")),
        topic_ids=[str(t) for t in (fm.get("topic_ids") or [])],
        aliases=list(fm.get("aliases") or []),
        parent_topic_id=str(parent) if parent else None,
        source_id=str(source_id) if source_id else None,
        source_kind=fm.get("source_kind"),
        source_metadata=fm.get("source_metadata"),
        inspection_status=fm.get("inspection_status"),
    )
