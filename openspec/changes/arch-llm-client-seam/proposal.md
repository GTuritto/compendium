## Why

Four factories select a stub-or-real model client with the same shape, copied four times:

- `answer/llm.py:158` `get_answerer` — `COMPENDIUM_SYNTH_STUB` → `StubAnswerer`, else `LLMAnswerer(synthesis_*)`
- `wiki/synth.py:83` `get_synthesizer` — `COMPENDIUM_SYNTH_STUB` → `StubSynthesizer`, else `LLMSynthesizer(synthesis_*)`
- `curate/extract.py:202` `get_extractor` — `COMPENDIUM_SYNTH_STUB` → `StubExtractor`, else `LLMExtractor(synthesis_*)`
- `index/embedder.py:64` `get_embedder` — `COMPENDIUM_EMBED_STUB` → `StubEmbedder`, else `OpenAIEmbedder(embeddings_*)`

Each repeats `os.environ.get(<flag>) → stub, else load_config() → real(config)`. Three share
`COMPENDIUM_SYNTH_STUB`; the embedder uses `COMPENDIUM_EMBED_STUB`. There is no single place
that answers "run every model seam offline" — the hermetic test tier and the launchd smoke
must set two flags and keep them in agreement.

This is the strategy-registry shape the prior arch fixes used (`EdgeType`, `PageKind`,
`SignalGenerator`): the variation (which stub, which builder, which flag) is real but expressed
as four hand-copied functions. The deepening consolidates the **selection** into one registry,
leaving the four adapters and their stubs — the deep seams reviews #1/#2 praised — untouched.

## What Changes

- **A model-client registry** (`compendium/model_clients.py`): one record per role
  (`answerer`, `synthesizer`, `extractor`, `embedder`) carrying its stub env-flag and two lazy
  builders (stub, real). `get_model_client(role)` reads the flag once and returns the stub or
  the real client. The builders are lazy thunks (imports inside the function bodies), so the
  registry module never imports the four client classes at load time — no import cycle.
- **A single offline switch** `COMPENDIUM_LLM_STUB`: when set, every role returns its stub.
  The existing `COMPENDIUM_SYNTH_STUB` / `COMPENDIUM_EMBED_STUB` flags keep working unchanged
  (the umbrella is an OR with each role's own flag) — so existing tests, `.env`, and docs are
  not disturbed.
- **The four `get_*()` factories become one-line delegations** to `get_model_client(role)`,
  kept as named entry points so no caller changes.

## Capabilities

### New Capabilities

- `model-client-seam`: one `get_model_client(role)` registry that owns the stub-vs-real
  selection for the four model clients, plus a single `COMPENDIUM_LLM_STUB` offline switch. The
  four named factories delegate to it; the adapters and stubs are unchanged.

### Modified Capabilities

<!-- No behaviour change. Same clients constructed from the same config, same per-role stub
flags still honoured. This relocates the selection logic into one registry and adds an umbrella
offline flag; it does not change what any seam returns or how a client is built. -->

## Impact

- **New code/files:** `compendium/model_clients.py` (the registry + `get_model_client`);
  `tests/test_model_clients.py`.
- **Modified files:** `compendium/answer/llm.py`, `compendium/wiki/synth.py`,
  `compendium/curate/extract.py`, `compendium/index/embedder.py` (the four factories delegate).
- **No schema migration. No new dependency. No CLI / output change.**
- **Out of scope:**
  - **Changing the four protocols** (`Answerer` / `Synthesizer` / `Extractor` / `Embedder`) or
    their stub bodies — the deep adapters stay.
  - **Adding a fifth role** (e.g. a reranker) — the registry just makes it cheap later.
  - **`pipeline._embedding_model_name()`** — it reads `COMPENDIUM_EMBED_STUB` only to label the
    trace `"stub"`; it constructs no client and stays as-is (it MAY also honour the umbrella
    flag for label correctness — decided in the Phase Plan).
  - **Removing `COMPENDIUM_SYNTH_STUB` / `COMPENDIUM_EMBED_STUB`** — they coexist with the
    umbrella; the rest of the suite and `.env` rely on them.
