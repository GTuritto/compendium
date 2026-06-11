# Spec — the chat-completion envelope

## ADDED Requirements

### Requirement: One construction site for OpenAI-compatible chat clients
`make_openai_client(endpoint, api_key)` SHALL be the only place the application
constructs an OpenAI chat client; the empty-key fallback (`"not-needed"`) lives
there. `grep -rn "OpenAI(" compendium/` matches only `model_clients.py` and
`index/embedder.py`.

#### Scenario: real clients construct through the seam
- **WHEN** `LLMAnswerer`, `LLMSynthesizer`, or `LLMExtractor` is built
- **THEN** its client comes from `make_openai_client` with the role's endpoint
  and key

### Requirement: One chat envelope with uniform token accounting
`chat(client, model, system, user, *, on_token=None)` SHALL return a
`Completion(text, input_tokens, output_tokens)`; when the response carries a
usage block those counts are used, else the char/4 heuristic over the user
message (input) and the text (output).

#### Scenario: buffered call
- **WHEN** `chat` is called without `on_token`
- **THEN** one non-streaming completion is created and its content and usage
  are returned

#### Scenario: streaming call
- **WHEN** `chat` is called with `on_token`
- **THEN** deltas are forwarded to the callback in order, and the usage from
  the final chunk populates the `Completion`

### Requirement: Public client protocols unchanged
`Answerer`, `Synthesizer`, and `Extractor` SHALL keep their existing method
signatures and stub implementations; callers and the hermetic test tier observe
no change.

#### Scenario: hermetic tier unaffected
- **WHEN** the full fast + golden tiers run with the stub flags
- **THEN** they pass without modification
