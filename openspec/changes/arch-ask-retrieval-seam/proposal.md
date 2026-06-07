## Why

`compose.ask()` carries a private `_retrieve` parameter (`answer/compose.py:205`) that exists
only for tests. When supplied, `ask` takes a divergent path: it composes over the caller's
`RetrievalResult` and **does not touch the database** — no `query_traces` row, no `ask_traces`
row (`trace_id=""`, `ask_trace_id=""`), and the context is built without a connection or vault
path (so page bodies are not read). The production path opens a connection, runs
`pipeline.run`, persists both traces, and builds context from the vault.

So a leading-underscore param forks the production function into two materially different
paths, and the path the unit tests exercise is not the one production runs. This is the
test-only-seam smell review #3 flagged (candidate 4).

Verified usage: `_retrieve` is used **only** in three unit tests in `tests/test_ask.py`
(72–119), which compose over a canned `RetrievalResult` with no database. The end-to-end tests
(249+) already avoid `_retrieve` — they `monkeypatch.setattr(pipeline, "run", …)` against a
test DB. So the two test needs are already distinct: **pure composition (no DB)** and
**full persistence (real DB)**.

The fix that fits both, and removes the production smell, is to make composition a first-class,
documented function rather than a hidden branch: extract `compose_answer(question, result, …)`
— exactly what the `_retrieve` branch does today — and make `ask()` single-path (always
retrieve + persist). The unit tests call `compose_answer` directly; `ask` loses `_retrieve`.

## What Changes

- **A public `compose_answer(question, result, *, answerer=None, on_token=None) -> AskResult`**
  in `compendium/answer/compose.py`: rewrite → build context (no DB) → compose/refuse →
  assemble with empty trace ids. This is the composition seam — the surface the unit tests
  target — promoted from the `_retrieve` branch to a named function.
- **`ask()` becomes single-path:** the `_retrieve` parameter and its branch are removed; `ask`
  always opens a connection, runs `pipeline.run`, persists the `query_traces` + `ask_traces`
  rows, and composes via the shared `_compose` helper. Production behaviour is unchanged.
- **The three unit tests** in `tests/test_ask.py` move from `ask(…, _retrieve=fn)` to
  `compose_answer(question, fn(query), …)`. The end-to-end tests are unchanged.

## Capabilities

### New Capabilities

- `ask-composition-seam`: `compose_answer` is the public, DB-free composition over a
  `RetrievalResult`; `ask` is the single-path orchestrator (retrieve → persist → compose) with
  no test-only parameter. The interface is the test surface — composition tests cross the same
  function production composes through.

### Modified Capabilities

<!-- No behaviour change to `ask`'s production path: same rewrite, retrieval, refusal threshold,
composition, and the same query_traces + ask_traces persistence. This removes the private
_retrieve fork and names the composition it hid. -->

## Impact

- **New code:** `compose_answer` in `compendium/answer/compose.py`; no new file.
- **Modified files:** `compendium/answer/compose.py` (extract `compose_answer`, drop
  `_retrieve` from `ask`); `tests/test_ask.py` (three unit tests call `compose_answer`).
- **No schema migration. No new dependency. No CLI / HTTP / MCP change** — the facade and
  transports call `ask(question, on_token=…)`, which is unchanged.
- **Out of scope:**
  - **A `Retriever` protocol with prod/fake adapters** (the roadmap's literal framing).
    Considered and not adopted — see the design: it would have a single production adapter
    (`pipeline.run`) and would force the DB-free unit tests onto a test database. The composition
    seam is the real seam here.
  - **Changing the refusal threshold, rewrite, citation, or persistence behaviour.**
  - **Re-retrieving inside `ask`** — still forbidden by ADR-003; `ask` reuses `pipeline.run`.
