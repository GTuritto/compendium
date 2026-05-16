"""Source inspection: the automated checks run before storage.

Classifies a parsed source ``passed``, ``passed_with_warnings``, or
``failed`` against the byte-size, text-yield, and encoding-sanity checks
from the source inspection checklist. Duplicate detection needs the
database and lives in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from compendium.ingest.adapters.base import ParsedSource
from compendium.ingest.hashing import estimate_tokens

PASSED = "passed"
PASSED_WITH_WARNINGS = "passed_with_warnings"
FAILED = "failed"

_RANK = {PASSED: 0, PASSED_WITH_WARNINGS: 1, FAILED: 2}

_REPLACEMENT_CHAR = "�"
_ENCODING_WARN_RATIO = 0.02
_ENCODING_FAIL_RATIO = 0.10


@dataclass(frozen=True)
class InspectionResult:
    """The outcome of inspecting a source."""

    status: str
    notes: str

    @property
    def is_failed(self) -> bool:
        return self.status == FAILED


def inspect(
    parsed: ParsedSource,
    raw_bytes: bytes,
    *,
    max_source_bytes: int,
    min_text_tokens: int,
) -> InspectionResult:
    """Inspect a parsed source and classify it."""
    status = PASSED
    notes: list[str] = []

    def escalate(new_status: str, note: str) -> None:
        nonlocal status
        if _RANK[new_status] > _RANK[status]:
            status = new_status
        notes.append(note)

    if len(raw_bytes) > max_source_bytes:
        escalate(
            FAILED,
            f"source is {len(raw_bytes)} bytes, over the "
            f"{max_source_bytes}-byte limit",
        )

    tokens = estimate_tokens(parsed.text) if parsed.text.strip() else 0
    if tokens == 0:
        escalate(FAILED, "no extractable text")
    elif tokens < min_text_tokens:
        escalate(
            PASSED_WITH_WARNINGS,
            f"low text yield: ~{tokens} tokens (under {min_text_tokens})",
        )

    if parsed.text:
        ratio = parsed.text.count(_REPLACEMENT_CHAR) / len(parsed.text)
        if ratio > _ENCODING_FAIL_RATIO:
            escalate(
                FAILED,
                f"text is {ratio:.0%} replacement characters (bad decoding)",
            )
        elif ratio > _ENCODING_WARN_RATIO:
            escalate(
                PASSED_WITH_WARNINGS,
                f"text contains {ratio:.0%} replacement characters",
            )

    return InspectionResult(status=status, notes="; ".join(notes) or "ok")
