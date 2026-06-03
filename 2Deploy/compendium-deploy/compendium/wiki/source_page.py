"""Deterministic generation of ``source`` pages.

A source page is built by a fixed template from the ``sources`` row and its
chunks: a metadata block plus a section outline with chunk-range citations.
No LLM is involved, so the page is reproducible and rebuildable.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from compendium.db import repository
from compendium.wiki.page import Page
from compendium.wiki.slug import slugify
from compendium.wiki.vault import write_page

_EXCERPT_CHARS = 200


def generate_source_page(
    conn: psycopg.Connection, source_id: str | UUID, *, vault_path: str
) -> Page | None:
    """Generate (or regenerate) the ``source`` page for a source.

    Returns the written page, or None when the source has no chunks.
    """
    source = repository.get_source(conn, source_id)
    if source is None:
        return None
    chunks = repository.get_chunks_for_source(conn, source_id)
    if not chunks:
        return None

    existing = repository.get_wiki_page_by_source_id(conn, source_id)
    if existing is not None:
        slug = existing["slug"]
        page_id = str(existing["id"])
    else:
        slug = slugify(source["title"], repository.existing_slugs(conn, "source"))
        page_id = ""

    page = Page(
        kind="source",
        title=source["title"],
        slug=slug,
        body=_render(source, chunks),
        id=page_id,
        status="canonical",
        generator="synth",
        source_id=str(source["id"]),
        source_kind=source["kind"],
        source_metadata=_source_metadata(source),
        inspection_status=source["inspection_status"] or "passed",
    )
    return write_page(conn, page, vault_path=vault_path)


def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(source.get("metadata") or {})
    for key in ("author", "year", "url", "identifier"):
        value = source.get(key)
        if value is not None:
            metadata.setdefault(key, value)
    return metadata


def _render(source: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
    lines = [f"# {source['title']}", ""]
    if source.get("author"):
        lines.append(f"- **Author:** {source['author']}")
    if source.get("year"):
        lines.append(f"- **Year:** {source['year']}")
    lines.append(f"- **Kind:** {source['kind']}")
    if source.get("url"):
        lines.append(f"- **URL:** {source['url']}")
    lines.append(f"- **Inspection:** {source['inspection_status'] or 'passed'}")
    lines.append(f"- **Chunks:** {len(chunks)}")
    lines += ["", "## Outline", ""]

    for section_name, section_chunks in _group_by_section(chunks):
        positions = [c["position"] for c in section_chunks]
        span = (
            f"chunk {positions[0]}"
            if len(positions) == 1
            else f"chunks {positions[0]}-{positions[-1]}"
        )
        excerpt = " ".join(section_chunks[0]["body"].split())[:_EXCERPT_CHARS]
        lines += [f"### {section_name}", "", f"{span}. {excerpt}...", ""]

    return "\n".join(lines).strip() + "\n"


def _group_by_section(
    chunks: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group position-ordered chunks into their contiguous sections."""
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for chunk in chunks:
        name = chunk["parent_section"] or "(unsectioned)"
        if groups and groups[-1][0] == name:
            groups[-1][1].append(chunk)
        else:
            groups.append((name, [chunk]))
    return groups
