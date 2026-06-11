## Why

The OpenAI chat-completion machinery is copied five times across the three real
model clients, and the client construction three times, byte-identical:

- `answer/llm.py:90`, `wiki/synth.py:59`, `curate/extract.py:183` —
  `OpenAI(base_url=endpoint, api_key=api_key or "not-needed")`
- the create-then-parse envelope: rewrite (`llm.py:94-108`), buffered compose
  (`llm.py:121-131`), streaming compose (`llm.py:133-154`), synthesize
  (`synth.py:62-79`), label (`extract.py:186-198`)

Token accounting (`Completion` + the usage-or-heuristic fallback) exists only in
the answerer; the synthesizer and extractor discard `response.usage`, so two of
the three paid LLM paths leave no token trail — an asymmetry `compendium
profile stats` now makes visible.

This deepens **behind** the model-client registry (arch-llm-client-seam, PR #54):
the registry keeps owning stub-or-real selection; this fix is what the *real*
clients share once selected.

## What Changes

- **One envelope in `compendium/model_clients.py`**: `Completion` (moved from
  `answer/llm.py`, re-exported there), `make_openai_client(endpoint, api_key)`
  (the one construction site, lazy import), and
  `chat(client, model, system, user, *, on_token=None) → Completion` (buffered
  or streaming with `include_usage`, usage-block-else-heuristic accounting).
- **The three real clients shrink to prompt assembly + result shaping**:
  `LLMAnswerer.rewrite/compose`, `LLMSynthesizer.synthesize`,
  `LLMExtractor.label` call `chat()`; the five envelope copies and three
  constructions are deleted. The synthesizer and extractor log their usage via
  structlog (`llm_usage` event) — persisting their counts to a table is out of
  scope (a later schema decision).
- **Public surface unchanged**: the `Answerer`/`Synthesizer`/`Extractor`
  protocols, every stub, every prompt, `_parse_labels`, and `get_model_client`
  keep their signatures; the hermetic tier cannot observe the change.

## Impact

- Affected: `compendium/model_clients.py`, `compendium/answer/llm.py`,
  `compendium/wiki/synth.py`, `compendium/curate/extract.py`, tests.
- One deliberate normalization, fallback-only: when the API returns no usage
  block, the input-token heuristic becomes `_approx_tokens(user_message)`
  uniformly (previously the answerer approximated from pre-template text).
  OpenRouter always returns usage, so recorded values do not change.
- The embeddings client (`index/embedder.py`) is a different API shape and
  stays put — explicitly out of scope.
