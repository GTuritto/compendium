## Context

Seventh post-v0.2 architecture-fix change, and Phase 3 of the review-#3 roadmap
(`Plans/arch-review-3-plan.md`). It consolidates the four stub-or-real model-client factories
behind one registry, the same shape fixes 2–4 used. Lowest-stakes of the roadmap: small, stable
duplication, behaviour-preserving. Independent of the other pending fix (Phase 4).

Deepening target: the **selection** wiring is copied four times. The adapters and stubs are deep
and stay. The win is **locality** (one place decides stub-vs-real and owns the offline switch)
and a small **leverage** (a fifth role is one registry entry).

## Goals / Non-Goals

**Goals:**

- One `get_model_client(role)` over a registry of the four roles.
- A single `COMPENDIUM_LLM_STUB` offline switch; per-role flags still honoured.
- The four `get_*()` delegate; callers unchanged.
- No import cycle; behaviour preserved.

**Non-Goals:**

- Changing the protocols or stub bodies.
- Removing the per-role env flags.
- Adding a new role.

## Decisions

### Decision: a registry with lazy builders (no import cycle)

`compendium/model_clients.py`:

```text
_UMBRELLA = "COMPENDIUM_LLM_STUB"

@dataclass(frozen=True)
class ModelRole:
    stub_env: str                    # the role's own offline flag
    make_stub: Callable[[], Any]     # lazy: imports the stub class inside
    make_real: Callable[[], Any]     # lazy: imports the real class + reads config inside

REGISTRY: dict[str, ModelRole] = {
    "answerer":    ModelRole("COMPENDIUM_SYNTH_STUB", _answerer_stub,   _answerer_real),
    "synthesizer": ModelRole("COMPENDIUM_SYNTH_STUB", _synth_stub,      _synth_real),
    "extractor":   ModelRole("COMPENDIUM_SYNTH_STUB", _extractor_stub,  _extractor_real),
    "embedder":    ModelRole("COMPENDIUM_EMBED_STUB", _embedder_stub,   _embedder_real),
}

def get_model_client(role: str) -> Any:
    r = REGISTRY[role]
    if os.environ.get(_UMBRELLA) or os.environ.get(r.stub_env):
        return r.make_stub()
    return r.make_real()
```

Each builder is a module-level thunk whose imports live **inside** the function:

```text
def _answerer_real():
    from compendium.answer.llm import LLMAnswerer
    from compendium.config import load_config
    c = load_config()
    return LLMAnswerer(c.synthesis_endpoint, c.synthesis_model, c.synthesis_api_key)
def _answerer_stub():
    from compendium.answer.llm import StubAnswerer
    return StubAnswerer()
```

Because the registry module imports none of the four client modules at load time, and each
`get_*()` lazily imports `model_clients`, there is no import cycle (the four client modules are
imported by `answer/`, `curate/`, `index/`, `wiki/` today and continue to be).

**Why not a central module that imports all four client classes at top level?** It would create
cycles (`answer/llm.py` → `model_clients` → `answer/llm.py`). Lazy thunks are the clean way to
keep one registry without inverting the existing import direction.

**Alternative considered — a thin `use_stub(role)` predicate only, leaving each `get_*()` to
build its own client.** Rejected as too thin: it removes only the `os.environ.get` literal and
still leaves four near-identical bodies. The registry is what makes a `get_*()` a one-liner and
a fifth role a single entry.

### Decision: the real builders read config through the section/primitive that exists today

`synthesis_*` and `embeddings_*` are top-level `Config` fields (not behavior sections), so the
real builders call `load_config()` for them exactly as the factories do now — unaffected by the
Phase 2 cached-section work (those fields were deliberately left on uncached `load_config()`).

### Decision: the four factories become one-line delegations

```text
# answer/llm.py
def get_answerer() -> Answerer:
    from compendium.model_clients import get_model_client
    return get_model_client("answerer")
```

Kept as named entry points so the ~dozen call sites (`compose.ask`, `synthesize_concept`,
`from_extracted_edges`, `pipeline`/`reindex` embedder use) do not change. The stub classes and
real classes stay in their current modules.

### Decision: the umbrella flag is an OR, additive

`COMPENDIUM_LLM_STUB` set → all four stub. It does not replace `COMPENDIUM_SYNTH_STUB` /
`COMPENDIUM_EMBED_STUB`; those still independently force their roles. So "all model seams
offline" is now one flag, while the existing two-flag usage across the test suite, `.env`, and
the launchd-env smoke note keeps working. (`project-smoke-launchd-env` can then prefer the single
flag.)

## Risks / Trade-offs

- **Low value, real churn.** Five files touched for a small duplication. Mitigation: the diff is
  mechanical and behaviour-preserving; parity tests pin each role's stub/real selection.
- **Naming.** The set includes the embedder, which is not an LLM. `model_clients` /
  `get_model_client` is chosen over `llm_clients` / `get_llm` for accuracy (open question, in
  case you prefer the roadmap's `llm` wording).
- **Trace label drift.** `pipeline._embedding_model_name()` reads `COMPENDIUM_EMBED_STUB` to
  print `"stub"`; if only the umbrella is set, the label would say the real model name. Minor;
  the Phase Plan decides whether to teach it the umbrella flag too.

## Migration Plan

Land `model_clients.py` + tests (no caller change), then repoint the four factories one file at
a time (each green against its suite), then update the launchd-env smoke note to the single flag.
Rollback = revert the branch.

## Open Questions

- Module/function name `model_clients` / `get_model_client` (plan — accurate, includes the
  embedder) vs the roadmap's `llm_clients` / `get_llm`? Plan: `model_clients`.
- Keep the four named `get_*()` entry points (plan — zero caller churn) vs migrate callers to
  `get_model_client(role)`? Plan: keep them.
- Teach `pipeline._embedding_model_name()` the umbrella flag for label correctness (plan — yes,
  one-line) or leave it on `COMPENDIUM_EMBED_STUB` only? Plan: teach it the umbrella.
