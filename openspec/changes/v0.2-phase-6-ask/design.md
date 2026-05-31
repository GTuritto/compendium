## Context

This change implements Phase 6 of `docs/COMPENDIUM_V0.2_BUILD.md`. It depends on the v0.1 retrieval pipeline (`compendium/retrieve/pipeline.py`), the v0.1 synthesis seam (`compendium/wiki/synth.py` — `get_synthesizer()`, the `SYNTHESIS_*` config), the Phase 5 query normalization (already wired in `pipeline.query`), and the v0.1 query-trace persistence (`query_traces`, `repository.insert_query_trace`). It does not depend on later v0.2 phases; Phase 7's access surface will import the Phase 6 composer through a shared facade.

`ask` is the first verb that composes an LLM answer. v0.1 stopped at ranked pages on purpose. The Phase 6 line is narrow: compose over what `query` already retrieves, cite the pages, refuse when coverage is thin, and trace every call. The composer is a thin layer; the page-first substrate does the retrieval.

## Goals / Non-Goals

**Goals:**

- A `compendium ask "<question>"` verb returning a structured `AskResult`: `{answer, refused, citations: [{ref, slug, title, trace_rank}], coverage_score, trace_id, ask_trace_id, gap}`, plus `suggested_actions` when refused.
- Reuse the existing `SYNTHESIS_*` config and the `pipeline.query` result; no parallel retrieval path.
- An LLM query-rewrite step (Shape D part 2) as the composer's first action, recorded on the trace.
- A refusal mode below `ask.refuse_below_coverage` (default `0.3`): no composition call, `gap` populated, `suggested_actions` names the next CLI command.
- An `ask_traces` row per call, joined to `query_traces` by `query_trace_id`, recording prompt template id, model, endpoint, token counts, cost estimate, and the answer text.
- Streaming output for interactive CLI use.

**Non-Goals:**

- The MCP / HTTP access surface (Phase 7, ADR-011).
- Multi-turn or conversational `ask`. Single question, single answer; no session state.
- Answer caching or memoization.
- A TUI screen for `ask`.
- pgvector-backed `ask`-trace similarity (deferred with the rest of pgvector).
- Autonomous semantic-edge extraction (Phase 8, ADR-010).

## Decisions

### Decision: the composer lives in a new `compendium/answer/` package

A new package `compendium/answer/` holds the composer (`compose.py` — `ask()` + the `AskResult` dataclass), the rewrite step (`rewrite.py`), and the prompt templates (`prompts.py`), mirroring the multi-module layout of `compendium/retrieve/`. The package name is `answer` rather than `ask` so the public function can be `answer.ask()` without a name collision, and so Phase 7's facade imports read naturally (`from compendium.answer import ask`).

**Alternative considered:** put `ask()` inside `compendium/retrieve/pipeline.py`. Rejected — `query` is LLM-free and on the hot path; folding an LLM composer into the same module blurs the cost boundary the whole design protects. A separate package keeps `query` auditable as the cost-free path.

### Decision: `ask` reuses `pipeline.query`, it does not re-retrieve

`ask` calls the existing `pipeline.query()` over the rewritten text and composes over its `RetrievalResult`. The `query_traces` row that `pipeline.query` already writes is the retrieval trace; the `ask_traces` row references it by `query_trace_id`. This guarantees the answer is grounded in exactly the pages a plain `query` would have returned, and that the two traces tell one coherent story.

**Alternative considered:** a bespoke retrieval path tuned for composition (e.g., more pages, different fusion). Rejected — divergence between what `query` returns and what `ask` answers over would make citations un-auditable and double the retrieval-tuning surface. One retrieval contract.

### Decision: refusal is computed from `coverage_score`, before any composition call

After `pipeline.query` returns, the composer reads `coverage_score`. If it is `< ask.refuse_below_coverage` (default `0.3`), the composer skips the composition LLM call entirely: `answer=null`, `refused=true`, `gap` carries the under-covered facet (from the query result's existing gap flagging), and `suggested_actions` names the natural next CLI command (`compendium ingest ...` when there are no covering pages; `compendium synth concept ...` when pages exist but coverage is thin). The rewrite call still runs (it precedes retrieval); only composition is skipped, so a refusal costs one LLM call, not two.

**Alternative considered:** always compose, then let the LLM self-refuse via the prompt. Rejected — a hard coverage gate is cheaper (no composition call), deterministic, and not subject to the model deciding to answer anyway. The threshold is config so the curator can tune the conservatism.

### Decision: the LLM query rewrite (Shape D part 2) is `ask`-only and runs before retrieval

The composer's first step asks the LLM to rewrite the question into a retrieval-friendly query (expand abbreviations, resolve pronouns, surface key terms). The rewritten text drives `pipeline.query`; the original question drives the composition prompt. The rewrite is gated by `ask.rewrite` (default `true`) so it can be disabled for debugging or cost control. `query` itself never rewrites — Phase 5's rule-based normalization stays the only transformation on the `query` hot path.

**Alternative considered:** push the rewrite into `query` so both verbs benefit. Rejected — it puts an LLM call on the cost-free `query` path, which is exactly what the Phase 5 grilling round ruled out (Shape D split: rule-based in `query`, LLM-based in `ask`).

### Decision: `ask_traces` is a new table referencing `query_traces`, not a column on it

A `query` produces a `query_traces` row whether or not it was issued through `ask`; an `ask` adds composition-specific data (prompt template, tokens, cost, answer text). Modeling that as a separate `ask_traces` table with `query_trace_id UUID REFERENCES query_traces(id)` keeps the query-trace schema unchanged and lets a single query trace exist without an ask trace (a plain `compendium query`). The migration is `0012`, `down_revision = "0011"`.

**Alternative considered:** widen `query_traces` with nullable `ask_*` columns. Rejected — it couples the two concerns, leaves most rows with null ask columns, and complicates the existing trace readers. A companion table matches the existing `promotion_events` / `query_traces` relational style.

### Decision: cost estimate is computed from token counts and a per-model rate table

`ask_traces.cost_estimate` is `input_tokens * rate_in + output_tokens * rate_out`, where the rates come from a small static table keyed by model name (a module constant in `compendium/answer/`, with a `0.0` fallback for unknown models and for the stub synthesizer). Token counts come from the LLM response usage block when present, else a tokenizer-free character/4 heuristic. The estimate is informational, not billing-grade.

**Alternative considered:** call a pricing API or omit cost. Rejected — a network pricing lookup adds a dependency and a failure mode for a number that only needs to be ballpark; omitting it loses the "is `ask` getting expensive?" signal the curator wants. A static table is good enough and easy to update.

### Decision: streaming for `text`, buffering for `json`

`compendium ask "<q>" --format text` streams the composed answer tokens to stdout as they arrive (the synthesis seam gains a streaming variant over the existing `httpx` client). The citations, trace ids, and coverage print after the streamed answer. `--format json` buffers the full answer and emits the single structured object, since a JSON consumer wants one parseable payload. On refusal there is nothing to stream; the structured refusal prints directly.

**Alternative considered:** stream the JSON as NDJSON chunks. Rejected — the CLI's JSON contract is one object per invocation (matching every other read verb); NDJSON would be a new shape. Streaming is a `text`-mode interactive affordance.

### Decision: `suggested_actions` is a small rule, not an LLM call

On refusal, `suggested_actions` is derived by a deterministic rule from the query result: zero covering pages → `["compendium ingest <source> --kind <kind>"]`; pages present but coverage thin → `["compendium synth concept \"<top page title>\""]`. No extra LLM call to generate suggestions.

**Alternative considered:** ask the LLM what to do next. Rejected — an extra call for a two-branch decision; the rule is predictable and free.

## Risks / Trade-offs

- **Composition quality depends on the synthesis model and the prompt.** The hermetic tier runs the stub synthesizer, so unit/integration tests verify structure (citations present, refusal triggers, trace written) not answer quality. Answer quality is verified by the curator in the smoke walk against the real model — outside the v0.2 Phase 6 hermetic acceptance, same posture as Phase 1 / Phase 5.
- **Two LLM calls per `ask` (rewrite + compose).** Cost roughly doubles vs a single-call design. Mitigated by the rewrite being gateable (`ask.rewrite=false`) and by refusal skipping composition. The `ask_traces` cost estimate makes the spend visible.
- **The coverage gate is a blunt instrument.** A question can be well-covered yet score below threshold (or thinly covered yet score above). The threshold is config; the operational doc explains tuning it. The gate protects against the worst case (composing over near-empty retrieval) rather than being a precise relevance judge.
- **Cost-estimate drift.** The static rate table goes stale as model pricing changes. It is informational and easy to edit; the operational doc names where it lives and that it is best-effort.
- **Streaming + trace ordering.** The `ask_traces` row (with token counts) is written after the stream completes, so a crash mid-stream leaves no ask trace. Acceptable: the `query_traces` row is already persisted by then, so retrieval is still audited; a partial answer with no ask trace is the correct record of an interrupted call.

## Migration Plan

`0012_ask_traces` creates the `ask_traces` table; `down_revision = "0011"`, `downgrade()` drops it. No change to existing tables, so the migration is additive and reversible. Applying it on the curator's host is a single `alembic upgrade head` (or the project's `compendium`-wrapped migration step). No data backfill: ask traces accrue from the first `compendium ask` after the migration.

Rollback is `alembic downgrade -1` (drops `ask_traces`) plus removing the `compendium/answer/` package, the `ask` subparser/handler, the renderer, the repository methods, the `ask:` config block, and the operational doc. The page-first `query` path is untouched, so retrieval behaviour is identical before and after.

## Open Questions — for the review gate

- **Composer package name.** Recommendation: `compendium/answer/` with `answer.ask()`. The curator may prefer `compendium/ask/` (function `run()` to avoid `ask.ask`).
- **Rewrite default.** Recommendation: `ask.rewrite=true` by default. The curator may prefer it off by default for cost until the rewrite prompt is tuned.
- **Refusal threshold.** Recommendation: `0.3` per the build plan. Confirm or adjust.
- **Cost-estimate rate table.** Recommendation: a static per-model table in code with a `0.0` fallback. Confirm the maintenance burden is acceptable vs omitting cost.
- **`suggested_actions` shape.** Recommendation: a list of copy-paste-ready CLI command strings. Confirm vs a structured `{verb, args}` shape that Phase 7's access surface might prefer.
