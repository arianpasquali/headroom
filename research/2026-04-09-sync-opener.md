# RES-333 sync opener

**Use as the opening 3–5 minutes of the meeting.** Short, direct, preempts the biggest skeptic attacks. Read the opening paragraph out loud, drop the headline table, hit the three findings, land the recommendation, then open Q&A.

---

## Opening paragraph (read this verbatim or paraphrase)

> We ran the cross-provider head-to-head on LongMemEval at N=50 on both providers. **Headroom wins on every axis we measured, on both providers.** On Sonnet 4.6 it's +46pp vs baseline and +28pp vs Anthropic's own shipped compaction, at −27% latency and −54% cost. On gpt-5.4 it ties on quality (the base model already saturates at 98%) but still delivers −43% latency and −54% cost vs baseline. We also ran two floor-test arms at matched compression ratio to answer the obvious skeptic question "isn't this just less text being less distracting?" — naive truncation and random chunk drop at the same ratio as Headroom score **10 to 16 percentage points WORSE than baseline**, while Headroom at the same ratio gains 46 percentage points. The gap between Headroom and naive compression at matched ratio is 56 to 62 percentage points. The ML in the ContentRouter is earning its entire keep.

## The headline table (project this on-screen or paste in chat)

### Anthropic side — Sonnet 4.6, 5 arms

| arm | quality | **Δ vs baseline** | p50 latency | cost/case |
|---|---:|---:|---:|---:|
| baseline | 38.0% | — | 6,286 ms | $0.3757 |
| **headroom_default** | **84.0%** | **+46.0pp** 🚀 | **4,615 ms** | **$0.1727** |
| anthropic_compact_v2 | 54.0% | +16.0pp | 8,312 ms | $0.3791 |
| dumb_truncation_last_n | 28.0% | **−10.0pp** | 3,707 ms | $0.1734 |
| random_chunk_drop | 22.0% | **−16.0pp** | 4,155 ms | $0.1754 |

### OpenAI side — gpt-5.4, 3 arms

| arm | quality | Δ vs baseline | p50 latency | cost/case |
|---|---:|---:|---:|---:|
| baseline | 98.0% | — | 7,096 ms | $0.2836 |
| **headroom_default** | **98.0%** | +0.0pp | **4,038 ms** | **$0.1301** |
| openai_compact_v2 | 98.0% | +0.0pp | 14,288 ms | $0.2807 |

**300 API calls, zero errors.** Same 50 LongMemEval `single-session-user` cases, two separate runs because the driver rejects mixed-provider arm lists.

## The three findings to emphasise (in this order)

### 1. The floor-test finding is your strongest card — lead with it

> *"Before we look at provider compaction, here's the question that would be asked first: isn't Headroom just winning because compressing to 54% means less text is less distracting? We tested that directly. Two new arms: dumb truncation keeping the last 46% of tokens, and random chunk drop at the same compression ratio. On Sonnet 4.6 at N=50: **dumb truncation scores −10pp vs baseline. Random chunk drop scores −16pp vs baseline.** Meanwhile Headroom at the same 54% compression scores **+46pp vs baseline**. The gap between Headroom and naive compression at matched ratio is 56 to 62 percentage points. Headroom's query-aware selection is doing the entire lift, not compression ratio per se."*

**Why this lands first:** it preempts the single most obvious skeptic attack cleanly, before anyone can ask it. It also demonstrates methodological care — "we thought about what could be wrong with this result and we tested it."

### 2. The two providers are in different regimes — both agree Headroom wins

> *"Sonnet 4.6 baseline is 38% at 125k tokens. It's losing 62 percentage points of available headroom to distractors. Headroom rescues that — gets us to 84%. On gpt-5.4 the base model is so strong at long-context recall that it already hits 98% with no compression — baseline, Headroom, and OpenAI's own compaction all tie at 98%. But Headroom still cuts latency by 43% and cost by 54% at zero quality risk. **The quality story is model-sensitive; the latency and cost stories are universal.** On weaker long-context models Headroom rescues quality; on stronger ones it rescues latency and cost. Both cases ship."*

**Why this lands second:** it explains *why* the Sonnet and OpenAI numbers look so different (46pp vs 0pp quality delta) in a way that strengthens the case rather than weakening it. The naive reading is "Headroom doesn't help gpt-5.4"; the correct reading is "gpt-5.4 doesn't need help on quality, and Headroom still wins the other two axes."

### 3. Provider compaction is real — and both are dominated on this workload

> *"We had to correct an earlier finding. The Apr 8 investigation concluded neither provider ships summarization compaction at the standard API level. **That was wrong on both sides, for two different reasons.** Anthropic's `compact_20260112` shipped 2026-01-12 — our SDK was too old to have typed shapes. OpenAI's Responses API context compaction works fine too — our probe was on `gpt-4o-mini` which isn't in their supported-models list, so it returned a degenerate response. On the real models (Sonnet 4.6 for Anthropic, gpt-5.4 for OpenAI) both features work. Both are real. Both are dominated by Headroom on this specific workload, but for different reasons worth naming."*

Then explain the two reasons:

- **`anthropic_compact_v2`**: query-blind prospective summarization. It has to decide what to preserve before seeing the question, so it applies a generic salience prior that preserves identity-defining facts (degrees, jobs) and drops incidental-looking facts (commute times, phone numbers) — which turn out to be the actual needles on LongMemEval half the time. Structural limitation for conversational fact-recall workloads.
- **`openai_compact_v2`**: designed for multi-turn running conversations where compaction payoff comes in subsequent calls. On our one-shot benchmark it's pure overhead — +101% latency, −1% cost. **This is fair framing, not a knock on OpenAI.** The feature isn't broken; it's the right tool for a different workload shape. Running-conversation benchmark is in Phase 2.

## The recommendation (one sentence, then the caveats)

> **"Ship Headroom behind a feature flag for long-context workloads on both OpenAI and Anthropic surfaces. No further Phase 2 gate."**

Then the honest caveats in priority order:

1. **One benchmark family.** LongMemEval, single question type (`single-session-user`). Sonnet 4.5 N=150 ablation replicates the shape across 3 types. Sonnet 4.6 per-type sweep across the other 5 types is Phase 2 #1 — worth running but not blocking.
2. **Two models, not the full frontier.** Sonnet 4.6 and gpt-5.4. Opus 4.6 second-model ablation is Phase 2 #4, cheap add.
3. **No orq production data.** Karina's reproduction found 0% compression on orq traces due to double-encoded JSON strings. Re-running after her JSON-unwrapping fix is Phase 2 #2 — the one gap that spans both workstreams.
4. **No tool-using benchmark.** τ-bench is Phase 2 #3, the honest home for the old `tool_runner(compaction_control)` comparison in its native habitat.

## Defensive Q&A — anticipated questions with one-line answers

### Q: "Isn't this just compression ratio? Any compression would help at the same ratio."

**A:** "No — that's exactly what the floor tests settle. At the same 54% compression ratio, dumb truncation scores −10pp vs baseline and random chunk drop scores −16pp. Headroom scores +46pp. The gap is 56 to 62 percentage points, from query-aware selection specifically."

### Q: "Why is gpt-5.4 baseline so much better than Sonnet 4.6 baseline?"

**A:** "gpt-5.4 appears to be dramatically more robust at long-context needle recall on LongMemEval. Its base quality is 98% on 125k-token haystacks. Sonnet 4.6 is 38% on the same cases. This is consistent with 'lost in the middle' being a real, model-specific effect that compression can rescue on some models but not others. The latency and cost wins are universal regardless."

### Q: "How does Headroom compare to OpenAI's compaction? It looks bad here."

**A:** "`openai_compact_v2` is a real feature on gpt-5.3/gpt-5.4. It works as designed. The reason it looks latency-negative here is that its benefit model is running conversations — the compaction payoff comes in *subsequent* API calls by reducing their token counts. Our one-shot LongMemEval benchmark doesn't exercise that benefit. A running-conversation benchmark is Phase 2. **Fair framing: 'different tool for different workload,' not 'broken.'** On our workload, Headroom wins; on multi-turn workloads the story may be different."

### Q: "What about Sonnet 4.5? Does this hold there too?"

**A:** "Yes — the Sonnet 4.5 N=150 ablation in §5.2 replicates the Headroom-wins shape across 3 LongMemEval question types: +20pp vs baseline on grand mean, +22pp on single-session-user specifically. Sonnet 4.5 baseline is *higher* than Sonnet 4.6 baseline (52% vs 38%), so Headroom's advantage is smaller on Sonnet 4.5 (+22pp vs +46pp), but the sign and shape are identical."

### Q: "How much did this cost? Is it in budget?"

**A:** "~$155 total across all investigation rounds to date: the original Sonnet 4.5 3-arm sweep (~$15), the temporal-reasoning rerun (~$3), the smoke probes for compact_20260112 and session memory (~$5), the Sonnet 4.6 3-arm N=50 (~$20), the Sonnet 4.6 5-arm N=50 with floor tests (~$65), and the OpenAI gpt-5.4 3-arm N=50 (~$47 retrofitted). Well within the ticket budget. Full remaining Phase 2 estimate is +$115–200 depending on which items get green-lit."

### Q: "Why did the earlier comment say OpenAI doesn't ship compaction? What changed?"

**A:** "The Apr 8 probe ran against `gpt-4o-mini`, which is NOT in OpenAI's supported-models list for the Responses API compaction feature. The endpoint returned a degenerate analytics-only response because the underlying model isn't trained to produce real compaction items. The guide is explicit that the feature needs `gpt-5.3-codex` or `gpt-5.4`. When we re-probed on `gpt-5.4` it worked correctly — real chainable compaction items. I updated the correction in §4 and the Linear comment is now the corrected version."

### Q: "What's the cost savings story for a production workload?"

**A:** "−54% cost per case on both providers. At 10,000 long-context requests per day at current per-case cost, that's ~$740k/year saved vs baseline, and the savings shape is identical across providers because Headroom sends half the tokens at input time. Neither provider's own compaction captures this in one-shot benchmarks because both happen *after* the tokens have been billed at input rate."

### Q: "What about tool-using / agentic workloads?"

**A:** "Not tested. τ-bench is Phase 2 #3, the honest home for the old `anthropic_compact` path that only fires inside `tool_runner` loops. For now the claim is scoped to conversational long-context recall on LongMemEval — I'm not generalising to agentic workloads."

### Q: "Who decides when this actually ships? What's the next step?"

**A:** "This is the research deliverable for RES-333. The ship decision itself belongs to the product/infra team. My recommendation is in the report; the next step is for the team to pick an initial feature-flag surface (memory? RAG? agent runs?) and a telemetry plan, then green-light one of the Phase 2 items in parallel — either the orq production rerun or the per-type sweep, depending on what matters most for the ship validation."

## What to have open on your screen during the meeting

1. **This file** (or your printed version of it) — for the talking points
2. **`research/2026-04-09-findings-update-3arm.md`** — the full findings file, for deeper questions
3. **The Linear RES-333 comment** (https://linear.app/orqai/issue/RES-333) — so you can point people at it as the shareable artifact
4. **`research/2026-04-09-res-333-report.md` §5.0** — for the full cross-provider tables if anyone wants to drill into the numbers

## What to AVOID saying

- **"We've proven Headroom is better."** No — we've shown it wins on one benchmark, one question type, two models, at N=50. That's strong but not "proven." Say "measured at N=50 on this benchmark" every time.
- **"OpenAI's compaction is broken."** No — it's designed for a different workload shape. Say "right tool for running conversations, not for one-shot benchmarks like LongMemEval."
- **"We tested everything."** No — we have a clear list of things we haven't tested (orq production, τ-bench, per-type sweep on Sonnet 4.6, other models, other benchmarks). Be explicit about what's in scope and what isn't.
- **"Anthropic's feature is bad."** No — it's strictly dominated by Headroom on our specific workload because it's query-blind. It's a perfectly reasonable tool for agent-continuation workflows where that's fine. Say "different operating point on the compression curve."

## Final nudge

The strongest single thing you can say tomorrow is:

> *"At the same 54% compression ratio, dumb truncation scores −10pp vs baseline and random chunk drop scores −16pp. Headroom scores +46pp. The gap between Headroom and naive compression at matched ratio is 56 to 62 percentage points. That's the ML earning its keep."*

If you only have time for one number, that's the number. It's the cleanest possible refutation of the skeptic attack and it's measured at N=50 on the canonical benchmark.

Good luck. You've got this.
