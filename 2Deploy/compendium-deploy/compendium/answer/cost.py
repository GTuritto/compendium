"""Best-effort cost estimation for ``ask`` (v0.2 Phase 6).

A static per-model rate table, USD per 1,000 tokens as ``(input, output)``.
Informational only, not billing-grade. Unknown models and the stub fall back to
zero. Edit the table as model pricing changes; it lives in code on purpose so it
needs no network lookup and no extra dependency.
"""

from __future__ import annotations

_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (0.003, 0.015),
    "anthropic/claude-sonnet-4.5": (0.003, 0.015),
    "claude-opus-4-8": (0.005, 0.025),
    "anthropic/claude-opus-4.8": (0.005, 0.025),
    "claude-haiku-4-5": (0.001, 0.005),
}


def estimate_cost(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float:
    """Estimate the USD cost of a call from token counts and the rate table."""
    rate_in, rate_out = _RATES.get(model, (0.0, 0.0))
    cost = (input_tokens or 0) / 1000 * rate_in + (output_tokens or 0) / 1000 * rate_out
    return round(cost, 6)
