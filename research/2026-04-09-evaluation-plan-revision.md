# RES-333 Evaluation Plan Revision — Anthropic compaction features

**Date:** 2026-04-09
**Author:** Arian Pasquali
**Status:** Draft — pending decision to execute before the RES-333 sync
**Related:**
- [`research/2026-04-09-res-333-report.md`](./2026-04-09-res-333-report.md) — the current RES-333 report that this plan revision corrects
- [`research/2026-04-09-streamlit-reproduction-comparison.md`](./2026-04-09-streamlit-reproduction-comparison.md) — the standalone comparison vs Karina's HF Space
- [Anthropic docs: automatic context compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Anthropic cookbook: session memory compaction](https://platform.claude.com/cookbook/misc-session-memory-compaction)

---

## Why this document exists

While prepping for the RES-333 sync, Bauke pushed back on our `summary_prompt` arm as a "baseline" — he was right, it's a specific implementation with a large free-parameter space, not a canonical comparison point. He asked whether we could use provider-native compaction as a proper baseline. When I dug into that question, two things surfaced that invalidate §4 of the current RES-333 report:

1. **Anthropic shipped `compact_20260112` on 2026-01-12** — a first-class, server-side compaction feature accessible via plain `beta.messages.create` with a beta header. It does not require tool calling, does not require a `tool_runner` loop, and is exactly the "proper baseline" Bauke originally asked for. **We did not test it.** Our installed `anthropic==0.76.0` SDK has no typed shapes for it; it's accessible through raw dict parameters on the beta endpoint.
2. **Anthropic published a cookbook pattern for session memory compaction** that uses prompt caching, proactive background summarization via threading, and a structured conversational schema. It's not a feature — it's Anthropic's *recommended* shape for how to do summarization-based compaction in conversational apps. Our current `summary_prompt` runner is a naive synchronous un-cached version of this pattern with the wrong schema (Feature A's SWE/planning shape instead of the cookbook's 6-section conversational shape).

Neither was in scope when I wrote the runners — the SDK source I read (`anthropic/lib/tools/_beta_compaction_control.py`) only knows about the old `tool_runner(compaction_control)` mechanism, which *is* tool-loop-gated. I extrapolated from the SDK source to "provider compaction is tool-loop-gated" without cross-checking the live docs. That inference was correct for the SDK surface we had and wrong for the live API.

This document captures the corrected plan. The current RES-333 report is still a valid finding on its own terms (Headroom beats uncompressed baseline by +22pp on N=50 `single-session-user`, +20.9pp grand mean across 6 types, on Sonnet 4.5). What's missing is the comparison against what Anthropic actually ships, and that comparison is now possible.

---

## Updated taxonomy — three Anthropic compaction mechanisms

| # | Mechanism | Where it lives | Gated by | Status in the current report |
|---|---|---|---|---|
| 1 | `tool_runner(compaction_control=...)` | Client-side SDK helper: `anthropic/lib/tools/_beta_compaction_control.py` | **Tool-runner iteration loop.** Fires on cumulative tokens inside an agentic tool loop. | Dropped from headline after the 22-min hang and pydantic errors. Kept as a documented dead-end. |
| 2 | `compact_20260112` via `context_management.edits` | **Server-side.** Plain `client.beta.messages.create(...)` with `betas=["compact-2026-01-12"]`. Released **2026-01-12**. | Nothing. Fires on any conversation that crosses the trigger token threshold. Default 150k, minimum 50k. **Models: Opus 4.6 / Sonnet 4.6 / Mythos Preview.** Not Sonnet 4.5. | **Never tested.** Missed entirely. SDK 0.76.0 has no typed shapes; accessible via raw-dict on the beta endpoint. |
| 3 | **Session memory pattern** (cookbook) | Client-side, user-space. Plain `messages.create` + `cache_control: ephemeral` + a background thread for proactive summarization. | Nothing — it's a documented pattern, not a feature. Anthropic endorses it as the recommended approach for long conversational apps. | **Never tested.** Our `summary_prompt` runner is a naive synchronous un-cached version of this pattern with the wrong schema. |

For OpenAI, nothing changes: `responses.compact()` is still an analytics/inspection endpoint (non-chainable `CompactedResponse`), and `responses.create(truncation="auto")` is still lossy first-N-drop that never fires below the context window. The one new thought: we could extract the `compaction_item` content from a `CompactedResponse` object and manually feed it as input to a fresh `responses.create()`. That would be a "manually triggered OpenAI compaction" arm. Not in the corrected headline plan, but added to Phase 2.

---

## What the cookbook pattern adds beyond the raw `compact_20260112` feature

The cookbook isn't "another compaction thing." It makes three specific design moves that the feature flag by itself doesn't, and each one creates a measurement obligation for the evaluation.

### 1. Proactive background compaction → user-visible latency ≠ wall-clock latency

The cookbook's headline pitch is **"instant compaction, no user wait"**: a background thread starts summarizing as soon as cumulative tokens cross a low threshold (e.g. 7.5k). By the time the user hits the hard limit, the summary is already in memory. **User-visible latency for compaction → 0 ms.** Total compute time is the same; the user just doesn't pay it.

Our current latency methodology measures wall-clock from "start of run" to "answer returned." For synchronous arms (`summary_prompt`, `compact_20260112` with default behaviour) this is the right number. For the cookbook pattern, **it unfairly penalises the arm** because we'd charge it for summary work that in production happens offline. We need a two-column latency measurement to make the comparison fair.

### 2. Prompt caching on the summarization call → dramatically cheaper and faster

The cookbook marks prior messages with `cache_control: ephemeral` so the background summarization reads 80–90% of its input from cache at $0.30/M instead of $3/M. Quoted from the cookbook:

```
Without caching: 5,000 tokens × $3/M              = $0.015 per update
With caching:    500 new + 4,500 cached @ $0.30/M = $0.003 per update
Savings: ~80% on background summarization costs
```

Our `summary_prompt` runner has **no caching.** Every summarization call pays full input price. If we report cost per case, the gap between "naive Feature A" and "cookbook pattern" on cost alone is ~5×. That's not a small effect.

We currently don't report cost per case at all. That has to change.

### 3. Different (conversational) schema

The cookbook uses a 6-section schema tuned for conversational apps:

```
## User Intent
## Completed Work
## Errors & Corrections
## Active Work
## Pending Tasks
## Key References
```

Feature A uses a 5-section schema tuned for SWE/planning: `decisions / constraints / rejected_paths / file_refs / facts`. Neither is ideal for LongMemEval's casual-fact question types ("what degree did I graduate with", "how long is my commute"), but the cookbook's shape is closer to conversational recall than Feature A's, and it's the shape Anthropic itself recommends.

Also worth noting: **the cookbook has no quality measurement at all.** Anthropic's own demo shows "88% token reduction" on a simulated creative-writing conversation. No benchmark, no judge, no accuracy number. That's a gap we can fill.

---

## Concrete plan changes

### A. Model pivot: Sonnet 4.5 → Sonnet 4.6

- `compact_20260112` requires Opus 4.6 / Sonnet 4.6 / Mythos Preview. It does not support Sonnet 4.5.
- The cleanest rerun is on **Sonnet 4.6**: one model, all arms, apples-to-apples.
- The current Sonnet-4.5 N=50 + per-type runs become a **model ablation appendix**. They remain useful as "does the +22pp gain hold on a slightly older model" evidence, but they stop being the headline.
- **Silver lining:** the rerun naturally tests whether the +22pp Headroom gain generalises to a newer-generation model with stronger long-context training. That was Phase 2 workstream 3 in the current plan. We get the answer for free on the same budget.
- **Opus 4.6** can be a second-model ablation in a follow-up run. Not blocking the headline.

### B. New headline arm list (4 arms)

| arm | what | status |
|---|---|---|
| **baseline** | Uncompressed full haystack, Sonnet 4.6 | keep |
| **headroom_default** | Headroom `ContentRouter`, Sonnet 4.6 | keep |
| **anthropic_compact_20260112** | Server-side, `beta.messages.create(betas=["compact-2026-01-12"], context_management={"edits":[{"type":"compact_20260112","trigger":{"type":"input_tokens","value":60000}}]}, ...)`, Sonnet 4.6, default Anthropic summary prompt | **NEW — the real provider-native baseline Bauke asked for** |
| **anthropic_session_memory** | Client-side cookbook pattern: proactive background summarization via threading, `cache_control:ephemeral` on prior messages, 6-section conversational schema, Sonnet 4.6 | **NEW — the real "proper summary prompt" baseline, with caching and the shape Anthropic recommends** |
| ~~summary_prompt (Feature A)~~ | Our original runner | **demote to appendix.** Keep as "naive first-cut with wrong schema and no caching" data point for the methodology section; drop from the headline table. |
| ~~anthropic_compact (tool_runner)~~ | Old SDK mechanism | **stays dropped** — already ruled out, recoverable only on τ-bench in Phase 2 |

### C. Two new columns in the results tables

**Current columns:** compression %, quality %, wall-clock p50 latency, Δ vs baseline.

**Added columns:**

- **User-visible latency (p50)** — for proactive/background mechanisms, exclude work that happens before the user's final question. For synchronous arms this equals wall-clock latency. For `anthropic_session_memory`, this strips the background summarization from the measured latency.
- **Cost per case** — sum of $(input + cached-read + output) for all API calls in a case, using Anthropic's published pricing. The `anthropic_session_memory` arm gets to claim its caching discount here.

Without these two columns, `anthropic_session_memory` is systematically under-credited and the comparison between it and `anthropic_compact_20260112` looks artificially even.

### D. Rewrite §4 "Pivot 2" in the main report

Current §4 claims:

> Neither provider ships summarization-based compaction at the standard API level for non-tool-using benchmarks.

**This is wrong for Anthropic as of 2026-01-12.** The rewrite needs to:

- **Correct the Anthropic portion.** `compact_20260112` does exist, does fire on plain `messages.create`, is summarization-based, and is applicable to non-tool benchmarks. We missed it because our SDK (0.76.0) has no typed shapes for it and I read the SDK source instead of the live docs.
- **Add the cookbook pattern as a separate category**: "recommended client-side compaction pattern." Document the 3 design moves (background threading, prompt caching, conversational schema).
- **Keep the OpenAI portion as-is** — `responses.compact()` is still an analytics endpoint; `truncation="auto"` is still lossy-drop. Add a Phase 2 bullet: manual extraction of the `compaction_item` from the `CompactedResponse` output, fed to a fresh `responses.create()`, would give a synthetic "OpenAI manual compaction" arm.
- **Reframe the overall conclusion.** The old version was: "there is a real market gap for Headroom because providers don't ship this." The corrected version: "Anthropic does ship it (one feature and one pattern); OpenAI doesn't; on Anthropic the real comparison is Headroom vs `compact_20260112` + the session memory pattern, and that comparison is now the open question this work needs to answer."

### E. Revise the TL;DR and Recommendation

**TL;DR change:** add a new final bullet making the open question explicit.

> Whether Headroom beats Anthropic's own shipped compaction (`compact_20260112` feature + session memory cookbook pattern) on Sonnet 4.6 is currently **unknown**. The experiment that would answer that is Phase 2 #0 and blocks the final verdict. The current +22pp and +20.9pp grand-mean numbers are "Headroom vs uncompressed baseline on Sonnet 4.5" — a necessary-but-not-sufficient finding.

**Recommendation change:**

- Old: "Ship Headroom behind a feature flag for long-context memory / RAG workloads."
- New: "Ship Headroom behind a feature flag for **OpenAI** long-context workloads (no provider-native alternative exists). For **Anthropic** workloads, gate the ship decision on the Phase 2 #0 4-arm rerun on Sonnet 4.6 — if Headroom still wins against `compact_20260112` and the session memory pattern at 55% compression and lower latency, ship. If it loses or ties, reframe Headroom as a model-agnostic pre-LLM layer whose value is provider independence plus cost savings at matched quality."

More honest, still positive on Headroom, but avoids overselling a result that has an obvious missing comparison.

### F. Phase 2 re-prioritisation

| Old # | New # | Workstream | Why it moved |
|---:|---:|---|---|
| — | **0** | **4-arm headline rerun on Sonnet 4.6** (baseline, headroom_default, anthropic_compact_20260112, anthropic_session_memory), N=50 on `single-session-user` plus per-type N=30 if budget permits | **Blocks the final verdict.** Was not in the old Phase 2 because we didn't know `compact_20260112` existed. |
| 1 | 1 | orq production rerun after JSON unwrapping fix lands | unchanged |
| 2 | 2 | τ-bench for `tool_runner(compaction_control)` | unchanged; now more clearly scoped — this is specifically for the SDK-side tool mechanism in its native habitat, not for the server-side feature (which is tested on LongMemEval in #0) |
| 3 | 3 | Opus 4.6 second-model ablation | unchanged; may be folded into #0 if we rerun on both Sonnet 4.6 and Opus 4.6 |
| — | 4 | **Dumb-truncation + random-chunk-drop baselines** at matched compression ratios (floor tests: if Headroom doesn't decisively beat these, something is wrong) | new, previously proposed in the summary_prompt discussion, now formalised |
| 4 | 5 | Multi-session Headroom ablation | unchanged |
| 5 | 6 | LongBench v1 + LLMLingua-2 head-to-head | unchanged |
| — | 7 | **OpenAI manual compact** — extract `compaction_item` from `CompactedResponse`, feed to fresh `responses.create(input=...)`, compare against uncompressed OpenAI baseline | new; cheap ~$10 |
| 7 | 8 | Separate RES ticket for Sonnet 4.5 temporal-reasoning collapse | unchanged |

### G. What stays the same

- **The rate-limit findings.** All errors in the original sweep were 429s on the baseline arm; compressed arms had zero. The rerun with rate-limit retry code validated the fix. Unchanged.
- **The temporal-reasoning rerun finding.** Baseline 0% at full N=30 is real; the 2/30 "win" is stochastic at the noise floor. Unchanged.
- **Headroom vs uncompressed** is still a valid standalone finding. It moves from "the headline" to "the model-ablation appendix" but the numbers don't change.
- **Karina's reproduction comparison** in §8 of the main report is unaffected — her work was Headroom-only regardless of which provider arms we run.
- **The dataset gate and LongMemEval choice** are unchanged.

---

## Cost and effort estimate

| Task | Effort | $ est |
|---|---|---:|
| Check PyPI for newer `anthropic` SDK with `compact_20260112` typed shapes; upgrade or write raw-dict wrapper | 30 min | — |
| Write `AnthropicCompactV2Runner` (~80 lines, similar shape to existing runners) | 1–2 h | — |
| Write `AnthropicSessionMemoryRunner` (cookbook pattern + threading + caching, ~120 lines) | 2–3 h | — |
| Add `user_visible_latency_ms` and `cost_usd` columns to `CompactionResult`, scoring, and report renderer | 1 h | — |
| Smoke test both new arms on N=2 each | 30 min | ~$3 |
| 4-arm N=50 rerun on `single-session-user` at Sonnet 4.6 | 30 min wall | ~$15 |
| Rewrite §4, §5, §7 of the main report; update TL;DR; add "Erratum" note at the top | 1 h | — |
| (Optional) per-type 4-arm sweep on Sonnet 4.6, N=30 × 5 types | ~2 h wall | ~$30 |
| (Optional) Opus 4.6 second-model run on the 4 arms, N=50 | ~30 min wall | ~$30 |

**Minimum for a defensible headline**: ~1 day of work + ~$18 ($3 smoke + $15 headline rerun).
**Full Sonnet 4.6 per-type sweep**: + $30.
**Both models (Sonnet 4.6 + Opus 4.6)**: + $60 total.

---

## Honest framing for the sync

The current report is a strong finding that's **partly wrong about the landscape**. Presenting the corrected version is actually a better story for the team, not a worse one:

> "We missed the live Anthropic feature because it post-dates our SDK. Here's what it is. Here's what it means for the RES-333 ask. Here are the real numbers from the rerun. Headroom still beats uncompressed baseline decisively. Whether it beats Anthropic's shipped compaction on Sonnet 4.6 is the question that actually needed answering and here's the answer."

Compared to the alternative:

> "Headroom beats Feature A on LongMemEval, but Feature A is a shaky baseline and we couldn't get provider compaction to fire because it's tool-loop gated."

The corrected version is crisper, more honest, and — if the rerun goes Headroom's way — a stronger endorsement. If the rerun doesn't go Headroom's way, we learn something more valuable than we would have learned from the current 3-arm headline.

**Owning the miss upfront makes the corrected result more credible, not less.**

---

## Decision to make

There are three execution options, in order of preference:

1. **Execute the full revision before the sync.** ~1 day of work + ~$18–48 depending on whether we also do the per-type sweep. Preferred if the sync is ≥24 hours away.
2. **Execute the minimum (headline 4-arm rerun only) before the sync.** ~4 hours of work + ~$18. Per-type sweep moves to Phase 2 proper. Preferred if the sync is in the next ~8–12 hours.
3. **Present the current 3-arm report at the sync with an upfront erratum** flagging the miss, then schedule the 4-arm rerun as the #0 Phase 2 workstream immediately after. Preferred only if the sync is within hours.

The runners, report edits, and rerun are fully self-contained in the `feat/compaction-compare` branch. None of this requires coordinating with anyone else on the team. The only external dependencies are:

- An `anthropic` SDK that can hit `beta.messages.create` with the `compact-2026-01-12` beta header (we may need to upgrade from 0.76.0, or pass raw dicts — both work).
- A Sonnet 4.6 API budget (we're well under RES-333's cost envelope even at the full option-1 cost).

**Recommendation: option 1 if time permits, option 2 as the fallback.**

---

## Next actions (if we proceed)

1. Check PyPI for newer `anthropic` SDK with `compact_20260112` typed shapes; upgrade if safe, or commit to the raw-dict path for now.
2. Smoke `compact_20260112` on 2 LongMemEval cases to verify it actually fires at ~60k trigger on Sonnet 4.6 and produces a usable `compaction` content block in the response. Verify the continuation semantics (append the response including the compaction block, then make the next call — the API should drop old blocks transparently).
3. Smoke the session memory pattern on 2 cases: background thread for summarization, `cache_control: ephemeral` on prior messages, 6-section schema, measure both wall-clock and user-visible latency.
4. Write `AnthropicCompactV2Runner` and `AnthropicSessionMemoryRunner`. Add `user_visible_latency_ms` and `cost_usd` to `CompactionResult` + the report renderer.
5. Run the 4-arm N=50 on `single-session-user` at Sonnet 4.6. Save to `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50/`.
6. Rerun `research/aggregate_by_type.py` (will need updates to handle multiple model roots) or write `aggregate_by_model.py`.
7. Rewrite §4, §5, §7 of the main report; add an "Erratum" note at the top of the report and of the standalone comparison; update the TL;DR and Recommendation.
8. Commit everything; open the sync with the erratum first.
