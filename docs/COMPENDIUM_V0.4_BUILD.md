<p align="center">
  <img src="logo.png" alt="Compendium logo" width="280">
</p>

# Compendium v0.4 — Validation Build Plan (draft)

Status: proposed, 2026-06-12. Successor to v0.3 (`v0.3.0`, commit `fcf7778`). This is the first plan whose deliverable is not a feature. v0.4 ships measurement and real use. It exists to answer one question the prior three plans built the machinery for but never asked: does the core bet hold against a real corpus.

## 1. The bet, restated as something that can fail

The whole project rides on one claim: a maintained wiki of stable, deduplicated, citable pages out-retrieves raw chunks over time. Three plans, fifteen ADRs, and four review rounds have hardened the engine around that bet. The bet has never been measured.

The naive test fails silently. Ingest the backlog, run real queries, watch coverage and recall climb, conclude the wiki works. That conclusion is unearned. On a growing corpus the metrics climb regardless, because every new source raises the odds the answer is somewhere in the index. Growth confounds the wiki effect completely. A rising curve on a single arm is not evidence for the thesis. It is evidence that more data is more data.

The thesis isolates only one way: run a chunk-only retrieval arm against the identical corpus snapshot and compare it to the page-first arm. The delta between the two arms on the same data is the wiki effect, with corpus size held constant. Everything else in this plan exists to make that comparison real, honest, and repeatable.

The control arm is therefore not a deferred nicety. It is the load-bearing instrument of v0.4. If it is hard to build, the rest of the plan is theater.

## 2. What v0.4 is not (exclusions)

Stack discipline applies to scope as much as to dependencies. The following are out, by decision, and a feature wanting in must argue past this list.

- **The ADR-012 scheduling absorption (review #5 candidate 1).** Deferred. It hardens the cadence and crash-recovery of a curation loop that has never run over a real corpus. The schedule's awkwardness is real and theoretical until the loop does enough work that timing matters. Revisit trigger: observed cadence pressure on real load, for example curate runs that overlap, fall behind, or miss material the daily ask habit then asks about. Amend ADR-012 if and when that trigger fires, not before.
- **Agent-memory writers (Ubongo, AgentTrader as callers).** Deferred to v0.5 or later. The undrawn line between agents ingesting and agents synthesizing or linking stays undrawn until the thesis has a verdict. Building shared memory on top of an unproven engine spends the entire deferred bundle to serve an engine you might rework or kill.
- **The deferred bundle: exposure, auth, namespacing, TLS, MCP-SSE, gRPC, pgvector.** Earned together, by the agent-memory case, which is itself deferred. Loopback and stdio stay.
- **A fifth surface, a new seam, another review round.** The cheap move with no plan to push against is more machinery. This plan is the harder move. No new pathways unless real use demands one.
- **Autonomous `SYNTHESIZES`.** Excluded forever by prior decision. Unchanged.

## 3. Track A — the corpus clock (starts day one, runs throughout)

Not code. The gating activity of the entire release.

Begin ingesting the real reading backlog immediately, on day one, before any phase below ships. Establish a daily ask habit against it. Let `ask_traces` accumulate untouched. This is the long-lead-time track, and its tempo is set by accumulation, not engineering. The harness phases cannot start until enough real queries exist to harvest a probe set from, so reading first is a hard dependency, not a suggestion. Instrumenting before real queries exist would mean inventing synthetic ones, which reintroduces the exact synthetic-fixture problem v0.4 exists to escape.

The profiler and `profile stats` were built for this observation work and have never seen real load. Turn them on here. This is the load they were waiting for.

Exit condition for Track A to unblock Phase 1: enough captured real queries to curate a stable probe set of roughly thirty to fifty questions that you actually asked and actually cared about the answers to.

## 4. Phase 0 — clear the deck (week one, parallel with Track A)

Cheap items that cost nothing and remove noise from the reviews. None of this is the point; all of it should be gone by the time the real measurement starts.

- **mutants verdict (candidate 3).** Delete the tree, gitignore the pattern. A mutation gate is a real complement to a suite whose live tier is skip-not-fail, but adopting one is its own project and not this quarter's. Remove it so it stops taxing every future explorer.
- **Wire-format snapshot test (candidate 2).** One frozen-bytes snapshot per facade verb, canned dataclass in, frozen JSON out, with the assertion comment naming the wire contract. Pure test work, zero behaviour risk. Do it because the knowledge "CLI render output equals API wire format" lives in one docstring and reviewers' heads, not because an agent caller is about to program against it. Twenty minutes of insurance, priced as insurance.
- **Cost table completion.** v0.4 is the first time real money flows through real synthesis at volume. The static table with a `0.0` fallback for unknown models silently undercounts every ask. Populate real prices for the models you actually run, and make an unknown model log a loud warning or a flagged estimate rather than reporting zero. You want to know what a day of real use costs.

## 5. Phase 1 — the single-point A/B (the fastest real verdict)

Depends on: Track A exit condition, plus the control arm built (can be coded during the Track A accumulation window).

This phase produces the first result that means something: on my real corpus, today, do curated pages beat raw chunks.

Build the control arm. Add a chunk-only retrieval mode that runs the existing BM25 plus dense fan-out and RRF fusion but bypasses page coverage, returning ranked chunks directly. The chunk machinery already exists as the page-coverage fallback, so this should be a pipeline flag and a return-shape choice, not new retrieval. Verify that assumption first. If chunk-only turns out to require real new code, stop and reassess, because the plan assumed it was cheap.

Harvest the probe set from `ask_traces`. Real questions, deliberately curated, frozen. This is not the golden set. The golden set is synthetic fixtures. The probe set is your actual queries, and it becomes the durable instrument you replay for the rest of the project's life.

Run the probe set through both arms against one identical corpus snapshot (use existing backup and restore to freeze the snapshot). Report the per-query delta, page-first minus chunk-only, on identical data. Per-query metrics stay strict. Do not lean on the aggregate MRR here: the flap is a measurement hazard, addressed in Phase 2.

Phase 1 gate: a per-query comparison table, page arm versus chunk arm, on a frozen real snapshot, with the deltas pre-registered criteria (section 7) can be read against.

## 6. Phase 2 — the compounding test (the slower, stronger claim)

Depends on: Phase 1 shipped, and months of continued Track A accumulation.

The thesis says the wiki advantage compounds over time, not just that it exists. Test that by replaying the frozen probe set through both arms at successive corpus milestones (50 sources, 200, 500, or whatever your real growth produces), each milestone a frozen snapshot. The claim survives only if the page-minus-chunk delta widens as the curated corpus grows. A flat delta is a real and useful null: it would mean pages help but do not compound, which downgrades the central bet to a smaller one.

This phase forces a fix the prior plans could defer. The aggregate MRR gate is informational because Qdrant HNSW insertion order flaps on small datasets. Longitudinal quality measurement cannot rest on a flapping aggregate. Either the real corpus is large enough that the flap stabilizes (plausible, denser graphs are more deterministic, but do not assume it), or you establish a measurement methodology robust to it: deterministic insertion order, fixed seeds, or multiple runs with confidence intervals rather than a single point. Decide this before the milestone numbers start carrying weight, because a noisy aggregate makes the compounding curve unreadable.

Phase 2 gate: a milestone-versus-delta chart for the page-minus-chunk advantage, with a stated methodology for the aggregate metric, read against the pre-registered compounding criterion.

## 7. Phase 3 — answer-quality judgment (conditional, do not pre-build)

Depends on: Phase 1 or 2 producing ambiguous retrieval deltas. Skip entirely otherwise.

Retrieval metrics measure whether the right pages came back. The thesis claims better answers. If the retrieval deltas are clear, retrieval stands as the proxy and this phase never ships. If they are ambiguous or contested, add an LLM-as-judge pairwise comparison of page-grounded versus chunk-grounded answers on the same probe queries, scored blind. This is the expensive, possibly unnecessary layer, gated explicitly on the cheaper layers failing to resolve. Building it speculatively would be the exact machinery trap this plan refuses.

## 8. Decisions you own before ingesting

- **Privacy and the supply chain.** Real ingestion sends your actual reading, some of it sensitive, to OpenRouter for every embedding and synthesis call. The local-first posture and the model supply chain have pointed opposite directions since v0.2 Phase 1, and ingesting your real life is what makes it concrete rather than philosophical. Decide consciously. If the corpus is sensitive enough, this is the moment to revisit local embeddings (the BGE-M3 absence from the Docker Model Runner catalogue is the original blocker), and that revisit would itself be an ADR.
- **Signal tempo.** Decide whether your organic backlog and query rate generate signal on a timeline you will actually wait for, or whether you manufacture load on purpose: a fixed reading list and a daily ask quota, to force the thesis into measurable range before patience runs out. This is the real v0.4 planning question and only you can answer it.
- **Pre-registered verdict.** Before the first PDF goes in, write down what page-minus-chunk delta counts as the wiki bet winning, what counts as a null, and what you do in each case (double down, rework retrieval, or kill the wiki layer and keep the engine as plain hybrid search). Self-validation rots without this. Pre-registration is the only thing standing between a real test and a slow slide into keeping the system because you built it.

## 9. ADRs this plan implies

- **Amend ADR-012** to record the scheduling absorption as deliberately deferred with a named revisit trigger, so the deferral is a decision on record rather than an open thread that haunts review #6.
- **New ADR for chunk-only retrieval mode.** Even measurement-only, it is a retrieval pathway, and the constitution says new pathways are ADR-gated. Scope it tightly: a control arm for validation, not a supported surface.
- **Optional ADR on validation methodology**, if Phase 2 forces a determinism fix or a confidence-interval approach to the aggregate metric. Worth recording because it changes what the golden gate means.

## 10. The one risk this plan runs

That the harness becomes its own machinery, a validation costume over the same instinct to build rather than use. The guards are explicit: Track A starts before any code and gates the phases; Phase 3 is conditional and never pre-built; the control arm is assumed cheap and the plan stops to reassess if it is not; and the deck-clearing in Phase 0 is named as not the point. If a quarter passes and the vault is still synthetic while the harness grows, the plan has failed in exactly the way the State doc warned: Compendium will have become a research platform instead of a useful tool. The corpus clock starting today is the whole defense against that.
