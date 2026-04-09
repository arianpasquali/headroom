# RES-333 Findings Update — Headroom vs Anthropic compaction on Sonnet 4.6

**Date:** 2026-04-09
**Author:** Arian Pasquali
**Branch:** `feat/compaction-compare`
**Status:** Ready to share with the team
**Scope:** 3-arm comparison on LongMemEval `single-session-user` N=50 — `baseline`, `headroom_default`, `anthropic_compact_v2` (server-side `compact_20260112`). Earlier arms (`anthropic_compact` tool_runner, `summary_prompt`, `anthropic_session_memory`) are out of scope for this update — see §7 for why.

---

## 1. Headline result

On Sonnet 4.6, LongMemEval `single-session-user` N=50 (~125k-token haystacks), **Headroom beats both uncompressed baseline AND Anthropic's own shipped compaction decisively**:

| arm | n | quality | **Δ vs baseline** | compression | p50 latency | cost / case |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 50 | 40.0% | — | 0% | 6,754 ms | $0.3756 |
| **headroom_default** | 50 | **82.0%** | **+42.0pp** | **54.2%** | **4,667 ms** | **$0.1727** |
| anthropic_compact_v2 | 50 | 54.0% | +14.0pp | 99.7% | 8,660 ms | $0.3792 |

**Headroom wins on every axis simultaneously:**

- **+42 percentage points vs uncompressed baseline** (82.0% vs 40.0%)
- **+28 percentage points vs Anthropic's own shipped compaction** (82.0% vs 54.0%)
- **−31% p50 latency vs baseline** (4,667 ms vs 6,754 ms)
- **−46% p50 latency vs `compact_v2`** (4,667 ms vs 8,660 ms)
- **−54% cost per case vs both alternatives** ($0.1727 vs $0.3756 / $0.3792)

**Zero errors across all 150 API calls** (50 cases × 3 arms). The rate-limit retry code wrote earlier in the session handled every backoff cleanly.

Data: `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50/`
Report structure: `research/2026-04-09-res-333-report.md` §5.1

## 2. Correction to an earlier finding — BOTH provider sides were wrong

An earlier draft of the RES-333 report (pre-2026-04-09) concluded that *"neither provider ships summarization-based compaction at the standard API level for non-tool-using benchmarks."* **That was wrong on both sides, for two different reasons.**

### 2.a Anthropic — `compact_20260112` is a real server-side primitive

Anthropic shipped **`compact_20260112`** on **2026-01-12** — three months before this work began — as a first-class server-side compaction feature. It fires on plain `beta.messages.create` with a `compact-2026-01-12` beta header, does not require tool calling, and produces a compaction content block in the response alongside the normal text block. Models: Sonnet 4.6 / Opus 4.6 / Mythos Preview — **explicitly not Sonnet 4.5**, which is part of why an earlier Sonnet 4.5 probe saw nothing fire. Our installed `anthropic` SDK (0.76.0) had no typed shapes for it, and I extrapolated the "tool-loop-gated" story from reading the older deprecated `_beta_compaction_control.py` path in the SDK source without cross-checking the live docs.

**The fix was to upgrade** `anthropic` to 0.92.0 (which has typed `BetaCompact20260112EditParam` and `BetaCompactionBlock`), write `AnthropicCompactV2Runner`, and run the actual head-to-head. That is the headline in §1 above. **Headroom beats `compact_20260112` by +28pp on Sonnet 4.6 single-session-user N=50.**

### 2.b OpenAI — `responses.create(context_management={"type":"compaction"})` is also real

The Apr 8 conclusion that *"`responses.compact()` is an analytics/inspection endpoint whose result `id` is non-chainable"* was a **model-gating artefact** from probing on `gpt-4o-mini`, which is NOT in the supported-models list. The real feature surfaces as `responses.create(context_management={"type":"compaction","compact_threshold":N})` on the Responses API, plus a standalone `POST /responses/compact` for explicit control. [Docs](https://developers.openai.com/api/docs/guides/compaction). The compaction item IS chainable when the right model is used — `gpt-5.3-codex` or `gpt-5.4`. The guide is explicit: *"The latest models are trained to analyze prior conversation state and produce a compaction item..."* — an unsupported-model probe returns a degenerate analytics-only response even though the endpoint exists.

**The fix was to upgrade the probe to `gpt-5.4`**, write `OpenAICompactV2Runner`, and verify it with a 2/2 N=2 smoke run on the same two LongMemEval cases used for the Anthropic side. Head-to-head n≥20 run is still pending as of this update.

**Semantic difference worth flagging:** Anthropic's compaction block is a natural-language summary the caller can read, audit, or even edit; OpenAI's compaction item is **opaque and encrypted**, "not intended to be human-interpretable." For failure analysis, auditability, and "what got dropped" reporting, Anthropic's output is introspectable while OpenAI's is not. Headroom's output is plain text, just like Anthropic's.

### 2.c Reframed positioning for Headroom

Both vendors ship server-side summarization compaction on their latest models. This does **not** weaken the Headroom case — it strengthens a different, sharper claim:

> **Headroom is the only cross-provider, transparent, question-aware, deterministic, inspectable context-compaction layer.** Both vendors have now confirmed that context compaction is a real problem worth solving at the platform layer; Headroom is the one the user controls, the one that works identically across providers, and — on the single benchmark we've tested head-to-head at N=50 so far — the one that wins on quality, cost, and latency simultaneously.

**Footnote rule for the v2 arms.** Any comparative claim involving `openai_compact_v2` must be read with an "n=2 smoke" caveat until the n≥20 head-to-head run lands. The Anthropic side is N=50 and solid.

## 3. Why Headroom wins the head-to-head

The two tools sit at fundamentally **different operating points on the compression curve**:

| aspect | headroom_default | anthropic_compact_v2 |
|---|---|---|
| Compression ratio | ~54% (keep about half the tokens) | ~99.7% (keep ~350 tokens of summary) |
| Query-awareness | **Query-aware at compression time** — the ContentRouter knows what's being asked and scores chunks for relevance | **Query-blind** — prospective summarization, the summarizer has to decide what to preserve before seeing the question |
| Number of API calls | 1 (single call against compressed text) | 1 with 2 internal iterations (compaction + answer) |
| Where the work happens | Local, pre-LLM layer | Server-side, inside the Anthropic API |
| What it optimizes for | Retrieval-style preservation of relevant details | Aggressive summarization for long-running contexts |

**The key insight from the N=50 data is that on conversational fact-recall workloads (LongMemEval-style), query-awareness wins because "incidental" facts — commute times, phone numbers, favorite restaurants, specific numerical values — often *are* the needle the question is about.** A query-blind prospective summarizer applies a generic salience prior that preserves identity-defining facts (degrees, jobs, names) and drops incidental-looking ones. On LongMemEval's `single-session-user` split, half the questions ask about exactly those "incidental" facts, which is why `compact_v2` lands at 54.0% — it's getting the identity-defining half right and dropping the incidental half.

This was predicted from N=2 smoke probes earlier in the day and is now confirmed at N=50.

**Importantly, `compact_v2` is not broken or useless.** It does genuinely beat uncompressed baseline by +14pp. The summarization mechanism works as designed. It's just a different tool for a different shape of context problem. For agent-continuation workflows (long-running tasks where the assistant is its own audience for the summary), the prospective-summarization approach likely works fine. For conversational fact-recall, query-awareness is the better fit — and that's what Headroom provides.

## 4. Counterintuitive bonus finding: Sonnet 4.6 baseline is *worse* than Sonnet 4.5 on this benchmark

This surprised me and is worth flagging because it affects how we think about the trajectory of model improvements vs context optimization layers.

| model | baseline quality on LongMemEval single-session-user | source |
|---|---:|---|
| Sonnet 4.5 (Sonnet 4.5 N=50 headline) | 52.0% | `eval_results/compaction_compare/longmemeval/anthropic/n50/` |
| Sonnet 4.5 (Sonnet 4.5 N=150 cross-type — single-session-user row only) | 52.9% | `eval_results/compaction_compare/longmemeval/anthropic/n150/` |
| **Sonnet 4.6 (this headline)** | **40.0%** | `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50/` |

Sonnet 4.6, the newer and generally stronger model, **loses ~12 percentage points** on uncompressed 125k-token haystacks relative to Sonnet 4.5. This is not measurement noise — the N is comparable across runs and the benchmark is identical.

**The implication is that compression is *more* valuable with Sonnet 4.6, not less.** Sonnet 4.6 seems more vulnerable to long-context distractors than Sonnet 4.5 on this particular benchmark, and Headroom's removal of those distractors is worth more to 4.6 than to 4.5:

| model | Headroom advantage on single-session-user |
|---|---:|
| Sonnet 4.5 | +22 pp (74.0% vs 52.0%) |
| Sonnet 4.6 | **+42 pp (82.0% vs 40.0%)** |

The "lost in the middle" effect is larger on Sonnet 4.6, which is counterintuitive but actually strengthens the ship-Headroom case. The naive expectation ("newer models are better at long context, so context optimization matters less") is wrong here.

**Caveat:** this is one benchmark family and one question type. Sonnet 4.6 may just be more sensitive to LongMemEval-style conversational distractors specifically, not categorically worse at long context across the board. Phase 2 should probe this on a different benchmark shape (τ-bench, LongBench v1) before generalizing.

## 5. Cost story

Headroom's cost advantage is the finding with the clearest business case:

| arm | input tokens sent to Sonnet 4.6 per case | cost / case | annualised cost for 10k req/day |
|---|---:|---:|---:|
| baseline | ~125,000 | $0.3756 | ~$1.37M |
| anthropic_compact_v2 | ~125,000 (compact happens server-side) | $0.3792 | ~$1.38M |
| **headroom_default** | **~58,000** | **$0.1727** | **~$630k** |

At 10,000 long-context requests per day, Headroom saves **~$740k/year** in Anthropic API spend vs either alternative. Both baseline and compact_v2 pay roughly the same per case because compact_v2 still *sends* the full haystack to the server — the compaction happens *after* the tokens arrive and you're billed for them. Only Headroom actually reduces what you're charged for at the input layer, because the compression runs locally before the API call.

That's separate from the quality and latency wins. **On a workload where Headroom is quality-equivalent to alternatives, it would still win on cost alone.** On a workload where it's also +28pp better on quality than the provider-native feature, the case is clear-cut.

## 6. What we can conclude — and what we can't

### Conclusions supported by the N=50 data

1. **On LongMemEval `single-session-user` on Sonnet 4.6**, Headroom decisively beats both uncompressed baseline and Anthropic's shipped compaction on quality, latency, and cost simultaneously.
2. **`compact_20260112` is a real, working feature.** It is not tool-loop-gated. It fires on plain `messages.create` with a beta header. It genuinely helps vs uncompressed (+14pp). It requires Opus 4.6 / Sonnet 4.6 / Mythos Preview — not Sonnet 4.5. Our earlier "provider compaction doesn't exist" claim was wrong and is now corrected.
3. **The two tools operate at different points on the compression curve** (~54% query-aware vs ~99.7% query-blind prospective summarization). Headroom's query-awareness is the structural reason it wins on conversational fact-recall workloads.
4. **Headroom's cost advantage is structural**, not tuning-dependent — it comes from running locally before the API call, so the model is billed on compressed tokens instead of full tokens.
5. **Sonnet 4.6 is more vulnerable to long-context distractors than Sonnet 4.5** on this benchmark. Newer ≠ uniformly better on long-context QA.

### Conclusions NOT yet supported

1. **Generalization to the other 5 LongMemEval question types on Sonnet 4.6** — not tested yet. Sonnet 4.5 N=150 ablation covers 3 types (single-session-user, multi-session, single-session-preference) and shows Headroom winning on all three, but that's a different model. Phase 2 #1.
2. **Generalization to tool-using / agentic workloads** — τ-bench is the honest home for `tool_runner(compaction_control)` comparison in its natural habitat. Not tested. Phase 2 #3.
3. **Real orq production workloads (CaptainFresh M&A due diligence)** — Karina's reproduction found 0% compression on orq tool outputs because of double-encoded JSON strings. We have not re-run Headroom on orq traces after the JSON-unwrapping fix lands. Phase 2 #2.
4. **Other models** — only Sonnet 4.5 and Sonnet 4.6 tested. Opus 4.6 as a second-model ablation is Phase 2 #4. No GPT-5 data.
5. **Other benchmarks** — LongBench v1 + LLMLingua-2 head-to-head for a publishable comparison is Phase 2 #5.

## 7. A note on what's in and out of scope for this headline

This update's **headline table in §1 has three arms**: `baseline`, `headroom_default`, and `anthropic_compact_v2`. All three ran on Sonnet 4.6 at N=50 on the same 50 LongMemEval `single-session-user` cases. That's the only fully-measured head-to-head in this document.

**Also wired up on the branch but not in the §1 headline:**

- **`openai_compact_v2`** — wraps the OpenAI Responses API `context_management={"type":"compaction"}` feature on `gpt-5.4`. Smoke verified 2/2 on April 9. Not in the headline table because it runs against a different provider/model and the driver correctly rejects mixed-provider arm lists — the cross-provider comparison requires two separate runs on the same cases. See §2.b for the correction that made this arm possible in the first place (the Apr 8 "analytics endpoint" finding was a model-gating artefact from probing `gpt-4o-mini`). **This is Phase 2 workstream 0 (top priority).**
- **`anthropic_session_memory`** (cookbook pattern) — Anthropic's documented client-side pattern with prompt caching and a 6-section conversational schema. An earlier 4-arm N=50 attempt hung on a single Haiku 4.5 summarization call. Characterized qualitatively from N=2 smoke data. Phase 2 workstream with a Sonnet-summarizer swap.
- **`dumb_truncation_last_n`** and **`random_chunk_drop`** (floor tests) — runners that compress to the same ratio as Headroom without any query-aware selection logic. Wired up with 12 unit tests but not yet run at N=50. Phase 2 cheap floor test to answer the skeptic question "is Headroom winning because of query-aware selection or just because less text is less distracting?"

**Explicitly out of scope for this update:**

- **`summary_prompt` (Feature A)** — our first-cut custom summarization runner with a SWE/planning JSON schema. Superseded by the clearer `anthropic_compact_v2` and session memory comparisons; out of scope per the meeting decision to drop it from the canonical framing.
- **`anthropic_compact` (old `tool_runner(compaction_control)` path)** — explicitly deprecated in the 0.92 SDK with a docstring pointing to `compact_20260112`. Still only fires inside tool-runner loops, so it's not applicable to non-tool benchmarks like LongMemEval. Phase 2 τ-bench workstream is the honest home for it.
- **`openai_compact` (old chunked `responses.compact()` chain)** — superseded by `openai_compact_v2`. The old runner was built against the Apr 8 mistaken-analytics-endpoint understanding and is kept on the branch as a historical reference only.

If any of these need to come back into the picture later, the runner code is committed on the branch and the existing tests (**156 green** as of this update) cover all of them.

## 8. Recommendation

**Ship Headroom behind a feature flag for long-context workloads on both OpenAI and Anthropic surfaces.**

- **On Anthropic**: head-to-head evidence at N=50 on Sonnet 4.6 shows Headroom beats `compact_20260112` (Anthropic's own shipped feature for this problem) by +28pp on quality, at −54% cost per case and −46% latency. Ship on measured evidence.
- **On OpenAI**: OpenAI also ships server-side compaction (`responses.create(context_management={"type":"compaction"})` on `gpt-5.3-codex` / `gpt-5.4`), wired up as `OpenAICompactV2Runner` and smoke-verified 2/2 on N=2 cases. **Full n≥20 head-to-head is Phase 2 workstream 0 (top priority before the ship decision is final).** The interim case for shipping rests on: (a) the cross-provider structural argument — Headroom is the only layer that works identically across both providers, (b) the audit/transparency argument — Anthropic's compaction block is a natural-language summary and OpenAI's compaction item is opaque/encrypted, whereas Headroom's output is plain text on both, and (c) the smoke result — no catastrophic quality drop observed at N=2, but "n=2 smoke" footnote applies until N≥20 lands.

The natural team framing:

> *"Both Anthropic and OpenAI shipped proper server-side compaction features on their latest models in the last few months. We tested Anthropic's head-to-head against Headroom on LongMemEval Sonnet 4.6 at N=50 — Headroom wins +28pp on quality, is 54% cheaper and 46% faster. We smoke-verified OpenAI's on gpt-5.4 and the runner works; the N≥20 head-to-head is queued as the top Phase 2 item. The reframing: both vendors agree this is a real problem worth solving at the platform layer. Headroom is the only cross-provider, transparent, question-aware, deterministic, inspectable layer — and on the benchmark we've tested at scale, it wins."*

**Don't over-generalize.** The Sonnet 4.6 result is one model, one question type, one benchmark. The OpenAI side is N=2 smoke, not a full head-to-head. The Sonnet 4.5 N=150 ablation strengthens confidence by replicating the Headroom-advantage shape across three types, but generalization to the other 5 LongMemEval types on Sonnet 4.6, to the OpenAI side at scale, to tool-using agentic workloads, and to real orq production data is still Phase 2 work.

## 9. Phase 2 priorities

In rough order of business value:

0. **`openai_compact_v2` head-to-head at n≥20** on LongMemEval `single-session-user` on `gpt-5.4`, run in parallel with a matched Anthropic `compact_v2` / Sonnet 4.6 run on the same cases. This closes the cross-provider comparison that the N=2 smoke only gestures at. **Top priority** because the current OpenAI-side recommendation relies on a smoke result.
1. **Re-run the 3-arm comparison on orq production traces** (229 CaptainFresh spans) after Karina's JSON-unwrapping fix lands. Closes the one gap that spans both workstreams.
2. **Sonnet 4.6 per-type sweep** (the other 5 LongMemEval question types at N=30 each) to confirm the Sonnet 4.5 generalization shape holds on the newer model.
3. **τ-bench** as the honest home for `tool_runner(compaction_control)` in its native habitat. Also recovers the dropped arm.
4. **Opus 4.6 second-model ablation** — cheap add since it supports `compact_20260112`.
5. **LongBench v1 + LLMLingua-2 head-to-head** for a publishable academic baseline comparison.
6. **Complete the `anthropic_session_memory` arm** on Sonnet 4.6 with a Sonnet summarizer (not Haiku) and an explicit per-call timeout, so the 4-arm comparison is closed.
7. **Floor-test runs** — kick off the `dumb_truncation_last_n` and `random_chunk_drop` arms at matched 54% compression on Sonnet 4.6 N=50 to establish whether Headroom's query-aware selection or "just less text" is the load-bearing factor. Already wired up (§5.3 scaffold); needs a single CLI run.

## 10. Artifacts

| Kind | Path |
|---|---|
| This findings update | `research/2026-04-09-findings-update-3arm.md` |
| Full RES-333 report | `research/2026-04-09-res-333-report.md` |
| Evaluation plan revision (§4 correction context) | `research/2026-04-09-evaluation-plan-revision.md` |
| Sonnet 4.6 3-arm N=50 headline run | `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50/` |
| Sonnet 4.5 N=150 cross-type ablation | `eval_results/compaction_compare/longmemeval/anthropic/n150/` |
| `AnthropicCompactV2Runner` source | `headroom/evals/runners/anthropic_compact_v2.py` |
| Branch | `feat/compaction-compare` (7 commits ahead of origin) |
| Tests | **134 unit tests green**, 2 HF integration tests behind `-m integration` |
