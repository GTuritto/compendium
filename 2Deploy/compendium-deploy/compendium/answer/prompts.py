"""Prompt templates for the ``ask`` composer (v0.2 Phase 6).

``PROMPT_TEMPLATE_ID`` is recorded on every ``ask_traces`` row so an answer can
be traced back to the exact prompt shape that produced it. Bump the id when a
template changes materially.
"""

from __future__ import annotations

PROMPT_TEMPLATE_ID = "ask-v1"

REWRITE_SYSTEM = (
    "You rewrite a user's question into a single concise search query for a "
    "wiki retrieval system. Expand abbreviations, resolve pronouns, and surface "
    "the key terms. Reply with only the rewritten query, no preamble, no quotes."
)


def rewrite_user(question: str) -> str:
    return f"Question: {question}\n\nRewritten search query:"


COMPOSE_SYSTEM = (
    "You answer questions strictly from the provided wiki page excerpts. Use no "
    "outside knowledge. Cite the pages you draw on inline by their bracket "
    "number (for example [1], [2]). If the excerpts do not support an answer, "
    "say so plainly. Write direct prose, no hedging, no em-dashes."
)


def compose_user(question: str, context: str) -> str:
    return (
        f"Wiki page excerpts:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the excerpts above, citing pages by bracket number:"
    )
