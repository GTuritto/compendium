# Design — arch-chat-envelope

## Home

`compendium/model_clients.py`. The registry already owns "how a model client is
selected"; the envelope is "how the selected real client is called". One module
answers both questions, and its lazy-import discipline (no openai import at
module load) extends naturally to `make_openai_client`.

## The envelope

    @dataclass
    class Completion: text: str; input_tokens: int; output_tokens: int

    def make_openai_client(endpoint: str, api_key: str) -> Any
    def chat(client, model, system, user, *, on_token=None) -> Completion

Buffered path: one `create()`, `choices[0].message.content or ""`, usage block
else heuristic. Streaming path (`on_token` given): `stream=True,
stream_options={"include_usage": True}`, deltas forwarded to `on_token`, usage
captured from the final chunk — ported verbatim from `llm.py:133-154`.

## What stays where (the seam's edges)

- Prompt assembly and templates: in each client class (they are the domain).
- Result shaping: `rewrite`'s `text or question` fallback stays in
  `LLMAnswerer`; `_parse_labels` stays in `extract.py`.
- Stub selection: untouched (`get_model_client`).
- `Completion` re-exported from `answer/llm.py` (`answer/__init__.py` and
  `compose.py` import it there today; no caller changes).

## Testing

`tests/test_chat_envelope.py` drives `chat()` with a fake client object (no
network, no SDK objects beyond duck types): buffered, streaming
(deltas + final-chunk usage), usage-absent heuristic fallback, empty-content
fallback, `make_openai_client` lazy construction args. The live tier
(`pytest -m live`) is the proof the envelope speaks real OpenRouter.
