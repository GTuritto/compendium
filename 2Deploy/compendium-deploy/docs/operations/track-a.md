<p align="center">
  <img src="../logo.png" alt="Compendium logo" width="220">
</p>

# Track A — the corpus clock (v0.4)

Track A is the gating activity of the entire v0.4 release. It is **not code**:
it is ingesting your real reading and asking real questions, day after day,
until enough real queries exist to harvest a probe set from. Everything in the
v0.4 measurement phases waits on it. Its tempo is set by accumulation, not
engineering.

This runbook is the operational half. The judgment half — what counts as the
bet winning, and whether your real reading may go to OpenRouter — is yours, in
[pre-registration.md](pre-registration.md). **Both decisions there must be
recorded before the first real PDF goes in.**

## Before you start (the §8 gates)

1. **Pre-registration** — fill in [pre-registration.md](pre-registration.md):
   the page-minus-chunk delta that counts as a win, a null, and a loss, and
   what you do in each case. This is the only thing standing between a real
   test and keeping the system because you built it.
2. **Privacy / supply chain** — record the decision in the same file. Real
   ingestion sends your actual reading to OpenRouter for every embedding and
   synthesis call. If the corpus is sensitive, revisit local embeddings (an
   ADR) before ingesting, not after.

## The daily loop

1. **Ingest.** Drop files into the inbox by kind:

   ```
   ~/Compendium/inbox/{book,article,paper,note,web}/
   ```

   The installed watcher (`compendium inbox install`) ingests each file with
   its parent-directory kind, routes it to `processed/<date>/` or
   `failed/<date>/`, and runs one `index sync` per event. For a URL or a
   one-off, `compendium ingest <path|url> --kind <kind>` still works.

2. **Ask, for real.** Use the question you actually have, through any surface:

   ```
   compendium ask "your real question"
   compendium web         # the browser surface, if you prefer
   ```

   Every ask writes an `ask_traces` row. Do not curate or harvest yet — let
   them accumulate untouched. Asking questions you don't care about poisons the
   probe set; only ask what you actually want answered.

3. **Let it run.** Keep ingesting and asking. The profiler is on (see below),
   so this is also the first real load `profile stats` has ever seen:

   ```
   compendium profile stats --days 30
   ```

## The profiler is on for Track A

The plan turns the profiler on here — this is the load it was built for. Set in
`.env`:

```
COMPENDIUM_PROFILE=1
```

Timed spans then log on every command; ingest stage durations persist to
`sources.metadata["stage_ms"]`; `compendium profile stats` aggregates the real
traffic. (A one-off run instead of the env flag: `compendium --timings <cmd>`.)

## Exit condition (what unblocks Phase 1's real run)

Enough captured real queries to curate a **stable probe set of roughly 30–50
questions** you actually asked and actually cared about the answers to.

When you are there:

```
compendium validate harvest                 # -> ~/.compendium/probes/candidates.yaml
# curate: prune to 30-50, label each probe's `expected` page slugs, set frozen: true
compendium backup                           # freeze the corpus snapshot (audit artifact)
compendium validate run --probes ~/.compendium/probes/probe-set.yaml
```

Read the report against [pre-registration.md](pre-registration.md). That is the
real Phase 1 verdict (the harness itself is already built and certified; so far
it has only run against the synthetic fixture set). See
[validation.md](validation.md) for the harvest → freeze → run mechanics.

## Then: keep accumulating for Phase 2

Phase 2 (the compounding test) replays the same frozen probe set at successive
corpus milestones (50 / 200 / 500 sources). It needs months more accumulation;
Track A simply continues. Each milestone is a `compendium backup` snapshot and
a `validate run`.

## The one discipline

If a quarter passes and the vault is still synthetic while the harness grows,
v0.4 has failed in the way the plan warns about — a research platform instead of
a useful tool. The corpus clock starting, and staying started, is the whole
defense. Ingest something real today.
