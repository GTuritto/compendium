# Composed answers (`compendium ask`)

`compendium ask "<question>"` returns an LLM-composed answer over the top-K wiki
pages, with page-anchored citations, a refusal mode, streaming output, and its
own trace row. It sits on top of the page-first substrate: it calls the same
`pipeline.query` that `compendium query` uses, composes over the pages that
query returns, and never re-retrieves. v0.2 Phase 6. The architectural framing
is the `ask` verb of ADR-011's access surface; Phase 6 ships it as a CLI verb
and a callable, and Phase 7 exposes it over MCP + HTTP through a shared facade.

## The composer flow

Three steps, in order:

1. **Rewrite (Shape D part 2).** When `ask.rewrite` is true (the default), one
   LLM call rewrites the question into a retrieval-friendly query — expanding
   abbreviations, resolving pronouns, surfacing key terms. The rewritten text
   drives retrieval; the original question drives composition. The cost-free
   `compendium query` hot path never does this; the rule-based Phase 5
   normalization is still the only transformation there.
2. **Retrieve.** `pipeline.query(rewritten)` runs the v0.1 page-first pipeline
   (BM25 + dense fan-out, RRF fusion, coverage scoring, fast-loop graph
   expansion, chunk fallback) and writes one `query_traces` row.
3. **Compose or refuse.** If the retrieval `coverage_score` is below
   `ask.refuse_below_coverage` (default `0.3`), `ask` refuses without a
   composition call (see below). Otherwise it composes an answer over the
   numbered page excerpts and attaches citations.

The LLM endpoint, model, and key reuse the `synthesis:` config block (the same
`SYNTHESIS_*` environment variables as `compendium synth`). Set
`COMPENDIUM_SYNTH_STUB=1` to use the deterministic stub answerer (no network,
no cost) — the hermetic test tier runs this way.

## The refusal contract

A refusal is a first-class outcome, not an error. The process still exits `0`.
Below the coverage threshold:

- `answer` is `null` and `refused` is `true`.
- No composition LLM call is made (the rewrite call still ran, so a refusal
  costs one LLM call, not two).
- `gap` carries the under-covered facet (`{kind, query, coverage_score,
  threshold}`, or the pipeline's own low-coverage gap when it fell back to
  chunks).
- `suggested_actions` names the natural next CLI command: an `ingest` command
  when no pages cover the question at all, or a `synth concept "<top title>"`
  command when pages exist but coverage is thin.

Tune the conservatism with `ask.refuse_below_coverage` in
`config/settings.yaml`. Raising it refuses more (favours "say nothing" over
"answer from thin retrieval"); lowering it answers more.

## Citations

Citations are structured and page-anchored, not free prose. Each carries:

- `ref` — the inline bracket marker the model is told to cite with (`[1]`,
  `[2]`, …).
- `slug` and `title` — the wiki page.
- `trace_rank` — the page's 1-indexed position in the retrieval's final
  ranking, so you can audit which retrieved page produced which claim.

The numbered page excerpts fed to the model use the same bracket numbers as the
citation `ref`s, so `[1]` in the answer maps to the citation with `ref="[1]"`.

## Streaming

`--format text` (the default) streams the composed answer to stdout token by
token as it arrives, then prints the citation block and the trace footer
(coverage, `trace_id`, `ask_trace_id`). `--format json` buffers the full answer
and emits a single structured object:

```json
{
  "answer": "…",
  "refused": false,
  "citations": [{"ref": "[1]", "slug": "…", "title": "…", "trace_rank": 1}],
  "coverage_score": 0.82,
  "trace_id": "…",
  "ask_trace_id": "…",
  "gap": null,
  "suggested_actions": []
}
```

A refusal streams nothing; the structured refusal prints directly in both modes.

## Reading an `ask_traces` row

Every `ask` writes one `ask_traces` row, joined to the retrieval's
`query_traces` row by `query_trace_id`:

```sql
SELECT a.*, q.query_text
FROM ask_traces a
JOIN query_traces q ON q.id = a.query_trace_id
ORDER BY a.created_at DESC
LIMIT 1;
```

Columns: `prompt_template_id` (the prompt shape that produced the answer, e.g.
`ask-v1`), `model`, `endpoint`, `input_tokens`, `output_tokens`,
`cost_estimate`, `answer_text`, `refused`, `created_at`. A refusal writes a row
too, with `refused=true` and a null `answer_text`. A plain `compendium query`
writes only a `query_traces` row (no `ask_traces` row) — the FK lets a query
trace exist without an ask trace.

## Cost estimate

`cost_estimate` is best-effort, not billing-grade: `input_tokens * rate_in +
output_tokens * rate_out`, summed across the rewrite and composition calls, with
rates from a static per-model table in [`compendium/answer/cost.py`](../../compendium/answer/cost.py).
Token counts come from the model's response usage block when present, else a
`len(text) // 4` heuristic (the streaming path falls back to the heuristic when
the endpoint sends no usage chunk). Unknown models and the stub estimate `0.0`.
Edit the rate table as model pricing changes; it lives in code on purpose so it
needs no network lookup and no extra dependency.

## Configuration

In `config/settings.yaml`:

```yaml
ask:
  refuse_below_coverage: 0.3   # below this retrieval coverage, refuse (no composition call)
  prompt_template_id: ask-v1   # recorded on every ask_traces row
  rewrite: true                # LLM query rewrite (Shape D part 2); ask-only
```

The LLM endpoint/model/key are not here — they reuse the `synthesis:` block.

## Out of scope (v0.2 Phase 6)

- The MCP + HTTP access surface (Phase 7, ADR-011).
- Multi-turn / conversational `ask`. Single question, single answer.
- Answer caching or memoization — every `ask` composes fresh and traces.
- A TUI screen for `ask`.
