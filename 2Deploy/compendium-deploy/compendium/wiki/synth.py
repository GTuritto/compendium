"""Concept and topic synthesis.

Synthesis gathers corpus chunks for a name, has a synthesizer write a page
body, appends a deterministic ``## Grounding`` section citing the chunks, and
writes the page. The synthesizer is either the real OpenAI-compatible client
or an injectable stub used by tests and offline verification.
"""

from __future__ import annotations

from typing import Any, Protocol

import psycopg

from compendium.db import repository
from compendium.wiki.page import Page
from compendium.wiki.slug import slugify
from compendium.wiki.vault import write_page

_CHUNK_LIMIT = 24

_SYSTEM_PROMPT = (
    "You write concise, well-grounded encyclopedia pages. Given excerpts "
    "from a corpus, summarize what the corpus collectively says about a "
    "concept. Use direct prose, no hedging, no em-dashes."
)


class SynthesisError(Exception):
    """Raised when synthesis cannot proceed (for example, no matching chunks)."""


class Synthesizer(Protocol):
    """Produces a page body for a name given grounding chunks."""

    def synthesize(self, name: str, chunks: list[dict[str, Any]]) -> str: ...


class StubSynthesizer:
    """A deterministic synthesizer for tests and offline verification."""

    def synthesize(self, name: str, chunks: list[dict[str, Any]]) -> str:
        sources = sorted({c["source_title"] for c in chunks})
        return (
            f"# {name}\n\n"
            f"{name} appears across {len(chunks)} chunk(s) drawn from "
            f"{len(sources)} source(s) in the corpus: {', '.join(sources)}.\n\n"
            "This page was assembled by the stub synthesizer; the Grounding "
            "section below lists the chunks it draws on."
        )


class LLMSynthesizer:
    """The real synthesizer: an OpenAI-compatible chat completion."""

    def __init__(self, endpoint: str, model: str, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=endpoint, api_key=api_key or "not-needed")
        self._model = model

    def synthesize(self, name: str, chunks: list[dict[str, Any]]) -> str:
        context = "\n\n".join(
            f"[{c['source_title']}] {c['body']}" for c in chunks
        )
        prompt = (
            f'Write a wiki page for the concept "{name}". Summarize what the '
            "corpus excerpts below say about it. Start with an H1 title.\n\n"
            f"Excerpts:\n\n{context}"
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""


def get_synthesizer() -> Synthesizer:
    """The stub when COMPENDIUM_SYNTH_STUB / COMPENDIUM_LLM_STUB is set, else the real client."""
    from compendium.model_clients import get_model_client

    return get_model_client("synthesizer")


def synthesize_concept(
    conn: psycopg.Connection,
    name: str,
    *,
    aliases: list[str] | None = None,
    vault_path: str,
    synthesizer: Synthesizer | None = None,
) -> Page:
    """Synthesize a concept page and write it to the vault."""
    return _synthesize(
        conn, "concept", name,
        aliases=list(aliases or []), vault_path=vault_path,
        synthesizer=synthesizer,
    )


def synthesize_topic(
    conn: psycopg.Connection,
    name: str,
    *,
    vault_path: str,
    synthesizer: Synthesizer | None = None,
) -> Page:
    """Synthesize a topic page and write it to the vault."""
    return _synthesize(
        conn, "topic", name, aliases=[], vault_path=vault_path,
        synthesizer=synthesizer,
    )


def _synthesize(
    conn: psycopg.Connection,
    kind: str,
    name: str,
    *,
    aliases: list[str],
    vault_path: str,
    synthesizer: Synthesizer | None,
) -> Page:
    synthesizer = synthesizer or get_synthesizer()
    chunks = repository.search_chunks(conn, [name, *aliases], _CHUNK_LIMIT)
    if not chunks:
        raise SynthesisError(f"no corpus chunks match '{name}'")

    prose = synthesizer.synthesize(name, chunks).rstrip()
    body = f"{prose}\n\n{_render_grounding(chunks)}"

    base_slug = slugify(name)
    existing = repository.get_wiki_page_by_slug(conn, kind, base_slug)
    if existing is not None:
        page_id = str(existing["id"])
        slug = base_slug
    else:
        page_id = ""
        slug = slugify(name, repository.existing_slugs(conn, kind))

    page = Page(
        kind=kind,
        title=name,
        slug=slug,
        body=body,
        id=page_id,
        status="draft",
        generator="synth",
        aliases=aliases if kind == "concept" else [],
    )
    return write_page(conn, page, vault_path=vault_path)


def _render_grounding(chunks: list[dict[str, Any]]) -> str:
    lines = ["## Grounding", ""]
    for chunk in chunks:
        excerpt = " ".join(chunk["body"].split())[:120]
        lines.append(
            f"- chunk `{chunk['id']}` ({chunk['source_title']}): {excerpt}..."
        )
    return "\n".join(lines) + "\n"
