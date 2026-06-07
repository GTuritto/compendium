# Tasks — arch-llm-client-seam

Behaviour-preserving: consolidate the four stub-or-real model-client factories behind one
`get_model_client(role)` registry with lazy builders, and add a single `COMPENDIUM_LLM_STUB`
offline switch (per-role flags still honoured). The four protocols + stubs are unchanged. No
schema migration; no new dependency; no output change. One commit per sub-phase, green at HEAD.
Boxes unchecked until implementation is approved.

## 1. The registry (sub-phase a)

- [ ] 1.1 `compendium/model_clients.py`: `ModelRole(stub_env, make_stub, make_real)`; a `REGISTRY` with the four roles (`answerer`, `synthesizer`, `extractor` → `COMPENDIUM_SYNTH_STUB`; `embedder` → `COMPENDIUM_EMBED_STUB`); lazy builder thunks (imports inside each); `get_model_client(role)` returning the stub when `COMPENDIUM_LLM_STUB` or the role's `stub_env` is set, else the real client. No top-level import of the four client modules (no cycle).
- [ ] 1.2 `tests/test_model_clients.py`: each role returns its stub when its own flag is set; the real type when no flag is set; `COMPENDIUM_LLM_STUB` forces every role to its stub; unknown role raises `KeyError`/`ValueError`.

## 2. The four factories delegate (sub-phase b)

- [ ] 2.1 `answer/llm.py::get_answerer`, `wiki/synth.py::get_synthesizer`, `curate/extract.py::get_extractor`, `index/embedder.py::get_embedder` each become a one-line delegation to `get_model_client(<role>)`. Stub + real classes stay where they are.
- [ ] 2.2 `pipeline._embedding_model_name()` honours `COMPENDIUM_LLM_STUB` too (returns `"stub"` under either flag) so the trace label stays correct.
- [ ] 2.3 Parity: each role builds the same client from the same config as before; existing `answer` / `wiki` / `curate` / `index` suites green; the hermetic tier still runs offline under the existing two flags.

## 3. Close-out (sub-phase c)

- [ ] 3.1 Grep gate: no `os.environ.get("COMPENDIUM_SYNTH_STUB")` / `COMPENDIUM_EMBED_STUB` stub-selection remains outside `model_clients.py` and `pipeline._embedding_model_name()` (the label reader).
- [ ] 3.2 `CONTEXT.md`: add **model client seam** as a first-class term (one `get_model_client(role)` registry; one `COMPENDIUM_LLM_STUB` offline switch; per-role flags coexist).
- [ ] 3.3 Append an "Arch — model client seam" smoke section to `tests/manual/smoke_test.md`: one `COMPENDIUM_LLM_STUB=1` runs `curate run` + `ask` fully offline; each per-role flag still forces its role.
- [ ] 3.4 Update the `project-smoke-launchd-env` guidance to prefer the single umbrella flag.
- [ ] 3.5 **Acceptance:** the stub-vs-real selection lives only in `model_clients.py`; the four `get_*()` delegate; `COMPENDIUM_LLM_STUB` runs every model seam offline while the per-role flags still work; fast tier and golden green; behaviour unchanged.
- [ ] 3.6 `openspec validate arch-llm-client-seam` clean.
