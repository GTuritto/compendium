## Why

v0.1 deliberately stopped short of composed answers: `compendium query` returns a ranked list of wiki pages with chunk citations, and the curator reads the pages. That was the right v0.1 line ("Not a chat UI and not LLM-composed answers"). v0.2's thesis is "better answers", and the build plan explicitly reverses that one line for a single new verb: `ask`. The page-first substrate stays exactly as it is; `ask` sits *on top of* it, composing an answer from the pages `query` already returns, with structured citations back to those pages.

Phase 6 also lands "Shape D part 2" — the LLM-based query rewrite that Phase 5 deliberately kept off the `query` hot path. Rewrite is an `ask`-only prompt step, so the cost-free `query` path is untouched and only `ask` (which already pays for an LLM call) absorbs the rewrite cost.

Three things define the phase:

1. **A composer that refuses when the wiki does not cover the question.** Below `ask.refuse_below_coverage` (default `0.3`) the answer is `null`, `refused` is `true`, the `gap` is populated, and `suggested_actions` names the natural next CLI command (ingest a source, synthesize a concept). Refusal is a first-class outcome, not an error — it protects the "answers grounded in the wiki" contract from hallucinating over thin coverage.
2. **Its own trace.** Every `ask` writes an `ask_traces` row joined to the `query_traces` row by `query_trace_id`, recording the prompt template id, model + endpoint, input/output token counts, a cost estimate, and the answer text. Tracing stays non-optional, mirroring the v0.1 query-trace and revision discipline.
3. **Structured, page-anchored citations.** The response is a structured object — `{answer, refused, citations: [{ref, slug, title, trace_rank}], coverage_score, trace_id, ask_trace_id, gap}` — not free prose. Citations point at the pages `query` ranked, with the `trace_rank` carried through so the curator can audit which page produced which claim.

## What Changes

- **A new `ask` composer** (`compendium/answer/`) exposing `ask(question, *, stream=False) -> AskResult`. It (a) LLM-rewrites the question (Shape D part 2), (b) runs the existing `pipeline.query` over the rewritten text, (c) composes an answer over the top-K pages using the same `SYNTHESIS_*` config as `synth`, (d) attaches structured citations, and (e) refuses below the coverage threshold.
- **A new `ask` CLI verb.** `compendium ask "<question>"` returns the structured response; `--format text|json` mirrors the other read verbs. Streaming output works for interactive CLI use (the text renderer streams tokens; `--format json` buffers and emits the final object).
- **An `ask_traces` table** (migration `0012`) with `query_trace_id UUID REFERENCES query_traces(id)`, `prompt_template_id`, `model`, `endpoint`, `input_tokens`, `output_tokens`, `cost_estimate`, `answer_text`, `refused`, `created_at`. A repository writer/reader pair (`insert_ask_trace`, `get_ask_trace`) mirrors the existing `insert_query_trace` shape.
- **A refusal mode.** When `coverage_score < ask.refuse_below_coverage`, no LLM composition call is made; `answer` is `null`, `refused` is `true`, `gap` carries the under-covered facet, and `suggested_actions` names the next CLI command.
- **An LLM query-rewrite step** (Shape D part 2) as the composer's first action. The rewrite is part of the `ask` prompt flow only; `query` is unchanged. The rewritten text is what drives the `pipeline.query` call and is recorded on the `ask_traces` row.
- **Config.** A new `ask:` block in `config/settings.yaml`: `refuse_below_coverage` (default `0.3`), `prompt_template_id` (default `ask-v1`), `rewrite` (default `true`). The LLM endpoint/model/key reuse the existing `synthesis:` block.
- **An operational document** `docs/operations/ask.md` covering the composer flow, the refusal contract, the citation shape, reading an `ask_traces` row, and the cost-estimate method.
- **A Phase 6 (v0.2) smoke section** appended to `tests/manual/smoke_test.md` with scenarios v0.2-6.1 → v0.2-6.x.
- **Tests.** Unit tests for the composer with the stub synthesizer (covered question → answer + citations; uncovered question → refusal + suggested actions; rewrite step). A migration round-trip test for `0012`. A repository round-trip test for `ask_traces`. An integration test exercising `ask` end-to-end against a populated test DB with the stub synth.

## Capabilities

### New Capabilities

- `composed-answers`: the `ask` composer (`compendium/answer/`) and `compendium ask` CLI verb; the LLM query-rewrite step (Shape D part 2); the structured `AskResult` shape with page-anchored citations; the refusal mode below the coverage threshold with `suggested_actions`; the `ask_traces` table (migration `0012`) joined to `query_traces`; streaming output for interactive CLI use; `docs/operations/ask.md`.

### Modified Capabilities

<!-- The v0.1 page-first retrieval contract (RRF fusion, top-page
coverage, chunk fallback, query-trace persistence) is preserved and
reused unchanged: `ask` calls `pipeline.query` and reads its result.
The only reversal is the v0.1 exclusion line "Not a chat UI and not
LLM-composed answers", which the build plan scopes to this single new
verb. `query` itself is untouched, including the Phase 5 rule-based
normalization; the LLM rewrite lives only in the `ask` flow. -->

## Impact

- **New code/files:** `compendium/answer/` (composer + rewrite + prompts + `AskResult`); `migrations/versions/0012_ask_traces.py`; `docs/operations/ask.md`.
- **Modified files:** `config/settings.yaml` (the `ask:` block); `compendium/__main__.py` (the `ask` subparser + handler); `compendium/cli/render.py` (an `ask` renderer); `compendium/db/repository.py` (`insert_ask_trace`, `get_ask_trace`); `tests/manual/smoke_test.md` (new § Phase 6 (v0.2)); `README.md` (one-line pointer); `CLAUDE.md` (v0.2 Phase 6 status + the reversed exclusion line pointing at the build plan); `docs/COMPENDIUM_V0.2_BUILD.md` Status section (Phase 6 merged entry).
- **One schema migration.** `0012_ask_traces` adds the `ask_traces` table; `down_revision = "0011"`. No change to existing tables.
- **No new runtime dependency.** The composer reuses the existing `httpx`-based LLM call shape from `compendium/wiki/synth.py` (the same `SYNTHESIS_*` config). Streaming uses the existing HTTP client's streaming response.
- **Cost.** `ask` makes up to two LLM calls per invocation (rewrite + compose) and zero on refusal (the rewrite still runs; composition is skipped). The stub synthesizer keeps the hermetic test tier free of network calls and cost.
- **Out of scope:**
  - **The access surface** (MCP + HTTP). `ask` is a callable function and a CLI verb in Phase 6; exposing it over MCP/HTTP is Phase 7 (ADR-011), which imports the same composer through the shared facade.
  - **Multi-turn / conversational `ask`.** Single question, single answer. No session state, no follow-ups.
  - **Autonomous semantic-edge extraction.** Phase 8 (ADR-010).
  - **A TUI screen for `ask`.** CLI + operational doc only in Phase 6.
  - **Answer caching / memoization.** Every `ask` composes fresh and writes a trace.
