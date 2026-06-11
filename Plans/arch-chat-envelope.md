# Phase Plan — arch/chat-envelope (review #4, Phase 1)

Umbrella: [arch-review-4-plan.md](arch-review-4-plan.md) Phase 1 · OpenSpec:
`openspec/changes/arch-chat-envelope/` · Branch: `arch/chat-envelope`

## Goal

One deep `chat(...) → Completion` envelope (plus one client-construction site)
behind the model-client seam; the three real LLM clients shrink to prompt
assembly and result shaping; the synthesizer and extractor stop discarding
token usage.

## Resolved decisions (umbrella flags closed here)

1. **Home = `compendium/model_clients.py`** (not a new module): the registry
   already owns model-client selection; the envelope is the call machinery for
   the selected real client. Lazy imports keep the no-import-cycle property.
2. **Fallback heuristic normalized** to `_approx_tokens(user_message)` for
   input tokens when no usage block arrives (fallback-only; OpenRouter always
   returns usage; recorded trace values unchanged).
3. **Synth/extract usage goes to structlog** (`llm_usage` event with role,
   model, token counts) — no schema change in this fix.

## Sub-phases

- **a — the envelope**: `Completion` + `_approx_tokens` + `make_openai_client`
  + `chat()` in `model_clients.py`; `tests/test_chat_envelope.py` (fake client;
  buffered, streaming with final-chunk usage, usage-absent, empty-content).
- **b — route the clients**: `LLMAnswerer.rewrite/compose`,
  `LLMSynthesizer.synthesize`, `LLMExtractor.label` over `chat()`; delete the
  five envelope copies + three constructions; `Completion` re-exported from
  `answer/llm.py` so `answer/__init__.py` / `compose.py` imports stand.
- **c — docs + smoke**: seams table row, C4 component note, DECISIONS +
  CHANGELOG, smoke section.

## Smoke test (appended to tests/manual/smoke_test.md)

`Arch — chat envelope`: stubbed `ask` / `synth concept` / `curate run`
unchanged; `grep -rn "OpenAI(" compendium/` → `model_clients.py` +
`index/embedder.py` only; live tier 2/2 on the primary host.

## Acceptance

Full fast + golden tiers green at each sub-phase HEAD; `pytest -m live` green;
`deploy/ci-smoke.sh` green; the grep above; ask citations/coverage output
byte-identical for the stub walk.
