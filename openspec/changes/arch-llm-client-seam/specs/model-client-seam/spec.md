## ADDED Requirements

### Requirement: One registry owns model-client selection

The system SHALL provide `get_model_client(role)` (`compendium/model_clients.py`) over a registry
of the four model roles (`answerer`, `synthesizer`, `extractor`, `embedder`), each declaring its
stub env-flag and lazy stub/real builders. The four named factories (`get_answerer`,
`get_synthesizer`, `get_extractor`, `get_embedder`) SHALL delegate to it. The registry module
SHALL NOT import the four client classes at load time (lazy builders), so it introduces no import
cycle. The protocols and stub implementations SHALL be unchanged.

#### Scenario: A role returns its real client by default

- **GIVEN** no stub flag is set
- **WHEN** `get_model_client(role)` is called for each role
- **THEN** it returns that role's real client (`LLMAnswerer` / `LLMSynthesizer` / `LLMExtractor` / `OpenAIEmbedder`) built from the same config the former factory used

#### Scenario: The named factories still work and delegate

- **WHEN** `get_answerer()` / `get_synthesizer()` / `get_extractor()` / `get_embedder()` are called
- **THEN** each returns the same client `get_model_client(<its role>)` returns — callers are unaffected

### Requirement: A single offline switch, with per-role flags preserved

`get_model_client(role)` SHALL return the role's stub when `COMPENDIUM_LLM_STUB` is set OR when
that role's own flag is set (`COMPENDIUM_SYNTH_STUB` for answerer/synthesizer/extractor,
`COMPENDIUM_EMBED_STUB` for embedder). The umbrella flag SHALL be additive — it does not replace
the per-role flags.

#### Scenario: The umbrella flag stubs every role

- **GIVEN** `COMPENDIUM_LLM_STUB` is set and the per-role flags are unset
- **WHEN** each role is resolved
- **THEN** every role returns its stub (the whole model surface runs offline from one flag)

#### Scenario: A per-role flag still forces only its role

- **GIVEN** only `COMPENDIUM_EMBED_STUB` is set
- **WHEN** the embedder and the synthesizer are resolved
- **THEN** the embedder returns its stub and the synthesizer returns its real client — the per-role flags keep their independent effect
