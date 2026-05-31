# Tasks — v0.2-phase-6-ask

Implements v0.2 Phase 6 of `docs/COMPENDIUM_V0.2_BUILD.md`. One schema migration (`0012`); no new runtime dependency. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. `ask_traces` schema + repository (6a)

- [x] 1.1 `migrations/versions/0012_ask_traces.py`: `CREATE TABLE ask_traces` with `id UUID PK`, `query_trace_id UUID REFERENCES query_traces(id)`, `prompt_template_id TEXT NOT NULL`, `model TEXT NOT NULL`, `endpoint TEXT NOT NULL`, `input_tokens INT`, `output_tokens INT`, `cost_estimate DOUBLE PRECISION`, `answer_text TEXT`, `refused BOOLEAN NOT NULL DEFAULT FALSE`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Index on `(query_trace_id)`. `down_revision = "0011"`; `downgrade()` drops the table.
- [x] 1.2 `compendium/db/repository.py`: `insert_ask_trace(conn, *, query_trace_id, prompt_template_id, model, endpoint, input_tokens, output_tokens, cost_estimate, answer_text, refused) -> str` mirroring `insert_query_trace`.
- [x] 1.3 `compendium/db/repository.py`: `get_ask_trace(conn, ask_trace_id) -> dict | None` and a join helper that returns the ask trace alongside its query trace.
- [x] 1.4 Migration round-trip test: `0012` upgrades and downgrades cleanly against the test DB; the table has the expected columns and FK.
- [x] 1.5 Repository round-trip test: `insert_ask_trace` then `get_ask_trace` returns the inserted row with the `query_trace_id` link intact.

## 2. The `ask` composer (6b)

- [x] 2.1 `compendium/answer/__init__.py`: re-export `ask` and `AskResult`.
- [x] 2.2 `compendium/answer/compose.py`: `@dataclass AskResult` carrying `answer: str | None`, `refused: bool`, `citations: list[Citation]`, `coverage_score: float | None`, `trace_id: str`, `ask_trace_id: str`, `gap: ... | None`, `suggested_actions: list[str]`; `@dataclass Citation` carrying `ref`, `slug`, `title`, `trace_rank`.
- [x] 2.3 `compendium/answer/compose.py`: `ask(question: str, *, stream: bool = False) -> AskResult` — (a) optional LLM rewrite (2.5); (b) `pipeline.query(rewritten)`; (c) read `coverage_score`; (d) below `ask.refuse_below_coverage` → refusal branch (no composition call); (e) else compose over the top-K pages; (f) attach citations from the query result's final ranking; (g) write the `ask_traces` row; (h) return `AskResult`.
- [x] 2.4 `compendium/answer/prompts.py`: the compose prompt template (id `ask-v1`) and the rewrite prompt template; the prompt template id is recorded on the trace.
- [x] 2.5 `compendium/answer/rewrite.py`: `rewrite_query(question, synthesizer) -> str` — one LLM call returning a retrieval-friendly query; gated by `ask.rewrite` (default `true`); passthrough when disabled.
- [x] 2.6 `compendium/answer/compose.py`: the composition LLM call reuses the `SYNTHESIS_*` config via `get_synthesizer()` (or a streaming sibling); token counts come from the response usage block when present, else a `len(text)//4` heuristic.
- [x] 2.7 `compendium/answer/cost.py` (or a module constant): a static per-model rate table; `estimate_cost(model, input_tokens, output_tokens) -> float` with a `0.0` fallback for unknown models and the stub.
- [x] 2.8 `suggested_actions`: a deterministic rule — zero covering pages → an `ingest` suggestion; thin coverage with pages present → a `synth concept "<top title>"` suggestion.
- [x] 2.9 Unit tests (stub synthesizer): covered question → `answer` populated, `refused=false`, ≥1 citation with `trace_rank`; uncovered question → `answer=null`, `refused=true`, `gap` populated, `suggested_actions` non-empty, no composition call made; rewrite step transforms the query and is recorded; `rewrite=false` is a passthrough.

## 3. CLI verb + render + config (6c)

- [x] 3.1 `config/settings.yaml`: add an `ask:` block — `refuse_below_coverage: 0.3`, `prompt_template_id: ask-v1`, `rewrite: true`. LLM endpoint/model/key reuse the `synthesis:` block.
- [x] 3.2 `compendium/config.py`: surface the `ask` config (mirroring how `retrieval` / `synthesis` are exposed).
- [x] 3.3 `compendium/__main__.py`: add the `ask` subparser (`ask "<question>"`, `parents=[fmt]`) and an `_ask` handler (parse → call `compendium.answer.ask` → render → print; exit non-zero only on hard error, not on refusal).
- [x] 3.4 `compendium/cli/render.py`: an `ask(result, fmt)` renderer — text mode prints the answer then a citations block then coverage/trace ids; refusal prints the gap + suggested actions; `--format json` emits the full `AskResult` object.
- [x] 3.5 Streaming: in `--format text` interactive mode the answer streams token-by-token; `--format json` buffers and emits the final object. Refusal has nothing to stream.
- [x] 3.6 Integration test: `compendium ask` end-to-end against a populated test DB with the stub synth — a covered question yields an answer + citations + an `ask_traces` row joined to a `query_traces` row; an uncovered question yields a refusal + an `ask_traces` row with `refused=true`.

## 4. Operational doc + smoke + acceptance close (6d)

- [x] 4.1 `docs/operations/ask.md`: sections — "The composer flow" (rewrite → query → compose); "The refusal contract" (threshold, `gap`, `suggested_actions`); "Citations" (the structured shape, `trace_rank`); "Reading an `ask_traces` row" (the join to `query_traces`); "Cost estimate" (the rate table, where it lives, that it is best-effort); "Streaming".
- [x] 4.2 Append the Phase 6 (v0.2) smoke section to `tests/manual/smoke_test.md` (scenarios v0.2-6.1 → v0.2-6.4).
- [x] 4.3 `README.md`: extend the v0.2 status sentence to mention Phase 6 and link `docs/operations/ask.md`.
- [x] 4.4 `CLAUDE.md`: status sentence catches up to Phase 6; the v0.2 phases bullet gains a Phase 6 entry; the "Not a chat UI and not LLM-composed answers" exclusion line is updated to point at the build plan's single-verb reversal.
- [x] 4.5 `docs/COMPENDIUM_V0.2_BUILD.md`: Status section gains a Phase 6 merged entry (PR number filled at merge).
- [x] 4.6 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 6: `compendium ask "<question>"` returns the structured response; the LLM call uses `SYNTHESIS_*`; below `ask.refuse_below_coverage` (default `0.3`) `answer` is `null`, `refused` is `true`, `gap` populated, `suggested_actions` names the next CLI command; an `ask_traces` row records template id, model + endpoint, token counts, cost estimate, and answer text, joined to `query_traces` by `query_trace_id`; the prompt's first step is the LLM query rewrite (Shape D part 2); streaming works for interactive CLI use; the smoke walk passes (covered question answered, uncovered refused, `ask_traces` row inspected).
- [x] 4.7 `openspec validate v0.2-phase-6-ask` clean.
