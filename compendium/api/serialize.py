"""The shared serializer for the access surface (v0.2 Phase 7).

The facade returns the existing dataclass shapes; both transports (HTTP and
MCP) turn them into JSON through ``to_payload`` here. It reuses the render
seam's ``to_json`` so the access-surface contract is byte-for-byte the CLI's
``--format json`` and cannot drift. The round-trip (serialize then parse) is
deliberate: one serializer, one contract.
"""

from __future__ import annotations

import json
from typing import Any

from compendium.cli import render


def to_payload(obj: Any) -> Any:
    """A JSON-ready structure (dict / list / scalar) for a facade result.

    Identical to ``compendium query --format json`` etc.: dataclasses become
    objects via ``asdict``, and non-JSON scalars (UUID, datetime) are
    stringified, exactly as the render seam does.
    """
    return json.loads(render.to_json(obj))
