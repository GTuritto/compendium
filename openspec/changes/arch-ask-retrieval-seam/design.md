## Context

Eighth post-v0.2 architecture-fix change, and Phase 4 (the last) of the review-#3 roadmap.
The review framed candidate 4 as "promote `ask`'s `_retrieve` hack to a real **Retrieval**
seam." On close inspection the faithful fix is a **composition** seam, not a retrieval one —
this design records why, since it reframes the approved candidate (the docs-first gate is where
that reframe gets your sign-off).

## Goals / Non-Goals

**Goals:**

- Remove the test-only `_retrieve` parameter from `ask`.
- Make composition a first-class, DB-free function (`compose_answer`) that the unit tests call.
- `ask` becomes single-path: always retrieve + persist. Production behaviour unchanged.

**Non-Goals:**

- A `Retriever` protocol / adapters (see the rejected alternative).
- Any change to retrieval, refusal, rewrite, citations, or persistence.

## Decisions

### Decision: extract `compose_answer`; make `ask` single-path

`ask` today has two branches. The `_retrieve` branch is exactly:

```text
result = _retrieve(retrieval_query)
context = _build_context(result, cfg["top_k"])        # no conn / vault
composed = _compose(question, result, context, answerer, on_token, cfg, rewrite_completion)
return _assemble(composed, result, trace_id="", ask_trace_id="")
```

Promote that to a public function:

```text
def compose_answer(question, result, *, answerer=None, on_token=None) -> AskResult:
    answerer = answerer or get_answerer()
    cfg = _ask_config()
    rewrite_completion = rewrite_query(question, answerer, enabled=cfg["rewrite"])
    context = _build_context(result, cfg["top_k"])
    composed = _compose(question, result, context, answerer, on_token, cfg, rewrite_completion)
    return _assemble(composed, result, trace_id="", ask_trace_id="")
```

`ask` drops `_retrieve` and its branch and keeps only the connection block (retrieve → persist
query trace → context-from-vault → compose → ask trace). The shared `_compose` / `_assemble` /
`_build_context` helpers are unchanged, so the production answer, citations, refusal, and both
persisted traces are byte-for-byte the same.

The unit tests call `compose_answer(question, canned_result, answerer=stub)` — the same thing
they got via `_retrieve` today, now through a named function instead of a private fork.

### Decision: do NOT add a `Retriever` protocol (the rejected alternative)

The roadmap said "Retrieval seam." A `Retriever` protocol (`retrieve(query) -> RetrievalResult`)
with `PipelineRetriever` (prod) + `FakeRetriever` (test) was considered and rejected:

- **One production adapter.** Retrieval in `ask` is always `pipeline.run`; there is no second
  real production retriever. By the deepening rule "one adapter = hypothetical seam, two = real
  seam," a `Retriever` protocol here is hypothetical.
- **It would push the DB-free unit tests onto a database.** If `ask` always persists (single
  path) and a `FakeRetriever` only swaps retrieval, the three composition unit tests would now
  need a test DB to reach `ask` — turning fast unit tests into store-dependent ones. The thing
  those tests actually vary is *composition over a result*, which the composer extraction
  captures directly.
- **The e2e tests already swap retrieval cleanly** via `monkeypatch.setattr(pipeline, "run", …)`
  — a normal test technique, not a production smell. No `Retriever` indirection is needed for them.

So the real seam the `_retrieve` fork was standing in for is the **composition**, not the
retrieval. Recording this so a future review does not re-suggest a `Retriever` protocol.

## Risks / Trade-offs

- **Reframes the approved candidate.** Mitigation: surfaced here at the docs-first gate; the
  outcome (no `_retrieve`, composition is a real testable surface) satisfies review #3's intent
  (kill the test-only fork) more faithfully than a single-adapter protocol would.
- **`compose_answer` returns empty trace ids.** That is correct — it does no persistence; the
  empty ids mirror today's `_retrieve` branch. Callers wanting traces use `ask`.

## Migration Plan

Extract `compose_answer`, delete the `_retrieve` branch + parameter, repoint the three unit
tests. One commit. Green against `tests/test_ask.py` (unit + e2e) and the fast tier. Rollback =
revert the branch.

## Open Questions

- Composition seam (`compose_answer`, plan) vs the roadmap's literal `Retriever` protocol?
  Plan: the composition seam — the `Retriever` protocol would be a single-prod-adapter seam and
  would force the unit tests onto a DB. **This is the one decision to confirm.**
- Name `compose_answer` (plan) vs `answer_over` / `compose`? Plan: `compose_answer`.
