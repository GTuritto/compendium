# Tasks — arch-chat-envelope

Behaviour-preserving (one fallback-only normalization recorded in the
proposal). One commit per sub-phase, green at HEAD.

## 1. The envelope (sub-phase a)

- [x] 1.1 `model_clients.py`: `Completion`, `_approx_tokens`,
  `make_openai_client`, `chat()` (buffered + streaming, usage-else-heuristic).
- [x] 1.2 `tests/test_chat_envelope.py`: fake-client buffered / streaming /
  usage-absent / empty-content / construction-args tests.

## 2. Route the three clients (sub-phase b)

- [x] 2.1 `answer/llm.py`: re-export `Completion`; `LLMAnswerer` uses
  `make_openai_client` + `chat`; delete the local envelope.
- [x] 2.2 `wiki/synth.py`: `LLMSynthesizer` likewise; log usage (`llm_usage`).
- [x] 2.3 `curate/extract.py`: `LLMExtractor` likewise; log usage.
- [x] 2.4 Full fast + golden tiers green; `pytest -m live` green on the
  primary host; `deploy/ci-smoke.sh` green.

## 3. Docs + smoke (sub-phase c)

- [x] 3.1 Seams table row + C4 note; `DECISIONS.md` + `CHANGELOG.md` entries.
- [x] 3.2 `tests/manual/smoke_test.md`: `Arch — chat envelope` section.
