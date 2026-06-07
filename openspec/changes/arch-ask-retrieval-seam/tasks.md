# Tasks — arch-ask-retrieval-seam

Behaviour-preserving: remove `ask`'s test-only `_retrieve` parameter by extracting the DB-free
composition it hid into a public `compose_answer(question, result, …)`, leaving `ask`
single-path (retrieve → persist → compose). The three composition unit tests call
`compose_answer`; the e2e tests are unchanged. No schema migration; no new dependency; no
CLI/HTTP/MCP change. One commit per sub-phase, green at HEAD. Boxes unchecked until approved.

## 1. Extract the composition seam (sub-phase a)

- [x] 1.1 `compendium/answer/compose.py`: add `compose_answer(question, result, *, answerer=None, on_token=None) -> AskResult` — rewrite → `_build_context(result, top_k)` (no conn/vault) → `_compose` → `_assemble(..., trace_id="", ask_trace_id="")`. This is the current `_retrieve` branch, named.
- [x] 1.2 Remove the `_retrieve` parameter and its branch from `ask`; `ask` keeps only the connection block (it always retrieves via `pipeline.run`, persists `query_traces` + `ask_traces`, and composes). The shared `_compose`/`_assemble`/`_build_context` helpers are unchanged.
- [x] 1.3 Update the `ask` docstring (drop the `_retrieve` line; point composition-only callers to `compose_answer`).

## 2. Repoint the tests + verify (sub-phase b)

- [x] 2.1 `tests/test_ask.py`: the three unit tests (covered-answer, uncovered-refuse, refusal-with-pages) call `compose_answer(question, result, answerer=…)` instead of `ask(…, _retrieve=…)`. The end-to-end persistence tests are unchanged.
- [x] 2.2 Parity: `ask`'s production path produces the same answer/citations/refusal and the same `query_traces` + `ask_traces` rows as before; the e2e tests still pass.
- [x] 2.3 Grep gate: no `_retrieve` remains in `compendium/` or `tests/`.

## 3. Close-out (sub-phase c)

- [x] 3.1 `CONTEXT.md`: note **Composed answer** is produced by `compose_answer` (DB-free) wrapped by `ask` (the single-path orchestrator); no test-only seam.
- [x] 3.2 Append an "Arch — ask composition seam" smoke line to `tests/manual/smoke_test.md`: `ask` still answers + refuses + persists both traces (no behaviour change); `grep _retrieve` is empty.
- [x] 3.3 **Acceptance:** `_retrieve` is gone; `compose_answer` is the DB-free composition seam the unit tests use; `ask` is single-path with unchanged production behaviour and persistence; fast tier and golden green.
- [x] 3.4 `openspec validate arch-ask-retrieval-seam` clean.
