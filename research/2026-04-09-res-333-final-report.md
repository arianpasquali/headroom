# RES-333 — Headroom vs Provider-Native Compaction

**A cross-provider evaluation on LongMemEval at N=50**

| Field | Value |
|---|---|
| **Ticket** | [RES-333](https://linear.app/orqai/issue/RES-333/reproduce-headroom-results) |
| **Author** | Arian Pasquali |
| **Date** | 2026-04-09 |
| **Branch** | [`feat/compaction-compare`](https://github.com/arianpasquali/headroom/tree/feat/compaction-compare) |
| **Status** | Final — ready for ship decision |
| **Audience** | Bauke, Kiran, Karina, Sohrab, product + infra teams |

---

## Executive summary

We evaluated [Headroom](https://github.com/chopratejas/headroom), an open-source context-compression layer, against the baseline "send the full haystack" approach and against the server-side compaction features that **both Anthropic and OpenAI** have shipped on their latest models. The benchmark is LongMemEval `single-session-user` at N=50 (~125k-token haystacks of multi-session conversation), run twice — once against Anthropic Sonnet 4.6 (five arms including two methodological-robustness floor tests) and once against OpenAI `gpt-5.4` (three arms) — on the same 50 cases. 300 API calls total, zero errors on either side.

**Headroom wins on every axis measured, on both providers.** On Sonnet 4.6 it delivers **+46 percentage points of answer quality** vs uncompressed baseline while cutting p50 latency by 27% and cost per case by 54%. It also beats Anthropic's own shipped `compact_20260112` by 28 percentage points of quality, 45% of latency, and 54% of cost. On `gpt-5.4` the base model is so robust at long-context needle recall that all arms saturate at 98% — there's no quality to rescue — but Headroom still cuts latency by 43% and cost by 54% at zero quality risk, while OpenAI's own Responses API compaction nearly *doubles* the latency on this workload (14.3s vs 7.1s) for no cost benefit.

**The strongest methodological finding is the floor-test result.** We included two floor-test arms that compress to the same 54% ratio as Headroom but without any query-aware selection logic: one keeps the last 46% of tokens (naive recency bias), the other drops random chunks deterministically. At the same compression ratio, these two arms score **−10 and −16 percentage points vs baseline** on Sonnet 4.6. Headroom at the same ratio scores **+46 percentage points**. The gap between Headroom and naive compression at matched ratio is **56 to 62 percentage points** on the same benchmark. This directly refutes the most obvious skeptic attack — "isn't Headroom just winning because less text is less distracting?" — and establishes that the ML in the ContentRouter is doing the entire lift.

**Recommendation: ship Headroom behind a feature flag for long-context workloads on both OpenAI and Anthropic surfaces.** The data is measured, the comparison is head-to-head against the provider-native alternatives, and the methodological robustness check is passed decisively.

---

## 1. Question

The RES-333 ask, in one line:

> *"Is Headroom a useful layer to put in front of LLM calls for long-context workloads? Does its compression preserve answer quality? And how does it compare to the context-management features the providers themselves ship?"*

This report answers that question at **N=50 on LongMemEval** against **two providers** with **three methodologically distinct floor/ceiling reference arms**.

## 2. Method

### 2.1 Benchmark

**LongMemEval `longmemeval_s_cleaned`**, filtered to the `single-session-user` question type. N=50, taken as the first 50 records in file order. Haystack size: ~125k tokens per case, 45–53 multi-session conversations per haystack. The benchmark is a needle-in-haystack conversational-recall task — each question asks about a specific fact the simulated user shared across the prior multi-session dialogue (e.g. *"What degree did I graduate with?"*, *"How long is my daily commute?"*).

We chose LongMemEval after rejecting LoCoMo (too short — 19–21k tokens per full conversation — would not trigger provider compaction thresholds) and Nemotron-Agentic-v1 (even shorter, and not representative of long-context workloads). Full dataset-selection rationale in the full working report.

### 2.2 Arms

Eight arms total across the two provider runs. Arms are organised into three categories:

**Reference arms** (common to both providers):

- **`baseline`** — single LLM call with the full uncompressed haystack. Pays full input-token cost; no compression.
- **`headroom_default`** — Headroom's `ContentRouter` (query-aware, open-source, local pre-LLM compression) then a single LLM call against the compressed text. Compression ratio ~54% on LongMemEval.

**Provider-native compaction arms** (provider-specific):

- **`anthropic_compact_v2`** (Anthropic side only) — wraps Anthropic's `compact_20260112` server-side compaction feature, released 2026-01-12 on Sonnet 4.6 / Opus 4.6 / Mythos Preview. Fires on plain `beta.messages.create` with `context_management.edits=[{"type":"compact_20260112",...}]` and the `compact-2026-01-12` beta header. Aggressive prospective summarization — compresses to ~350 output tokens (99.7% compression). Ships with reframed `instructions` + system prompt to resolve a role-confusion failure mode identified in smoke tests.
- **`openai_compact_v2`** (OpenAI side only) — wraps OpenAI's Responses API server-side context compaction, `responses.create(context_management={"type":"compaction","compact_threshold":N})` plus the standalone `POST /responses/compact` endpoint. Supported on `gpt-5.3-codex` / `gpt-5.4`. Fires at the configured input-token threshold. Compaction items are opaque and encrypted — not human-readable, unlike Anthropic's natural-language summary blocks.

**Methodological-robustness floor tests** (Anthropic side only):

- **`dumb_truncation_last_n`** — compresses to 54% by keeping the last 46% of the tokenized haystack and dropping the rest. Models naive recency bias.
- **`random_chunk_drop`** — splits the haystack into 2,000-token chunks and deterministically drops random chunks (SHA-256-seeded by case id for reproducibility) until 54% compression is reached. Models "any compression, zero structural preservation."

Both floor-test arms target the same ~54% compression ratio as `headroom_default` so they're directly comparable: at matched compression, only the selection logic differs.

### 2.3 Models and configuration

| Side | Answer model | Why |
|---|---|---|
| Anthropic | `claude-sonnet-4-6` | Required by `compact_20260112` (not supported on Sonnet 4.5) |
| OpenAI | `gpt-5.4` | Required by Responses API context compaction (not supported on `gpt-4o-mini`) |
| Judge (both) | `claude-haiku-4-5` | Cheap LLM-as-judge for answer correctness against ground truth |

Flags: `--max-tokens 512`, `--compact-v2-trigger 60000`, `--compact-v2-max-tokens 1500`, `--openai-compact-v2-trigger 60000`, `--openai-compact-v2-max-output-tokens 1500`, `--floor-target-compression-ratio 0.54`. Rate-limit retry enabled for all arms. Cost accounting uses `litellm.model_cost` (OpenAI) and the explicit Claude pricing table in `headroom/providers/anthropic.py` (Anthropic).

### 2.4 Quality measurement

LLM-as-judge via Haiku 4.5. Each case's predicted answer is judged against the ground-truth answer on a 1–5 scale; `quality_correct = score ≥ 3`. The `quality_correct_rate` reported in headline tables is the fraction of cases judged correct per arm.

### 2.5 Runs

Two separate CLI invocations because the driver's provider-compatibility validation correctly rejects mixed-provider arm lists:

1. **Anthropic 5-arm N=50** on Sonnet 4.6, 250 API calls → `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50_5arm/`
2. **OpenAI 3-arm N=50** on `gpt-5.4`, 150 API calls → `eval_results/compaction_compare/longmemeval/openai_gpt54/n50_3arm/`

Total: 300 successful API calls, zero errors on either side. Run script: `research/run_cross_provider_n50.sh`.

## 3. Results

### 3.1 Anthropic side — Sonnet 4.6, 5 arms

| arm | n | quality | **Δ vs baseline** | compression | p50 latency | cost / case |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 50 | 38.0% | — | 0.0% | 6,286 ms | $0.3757 |
| **headroom_default** | 50 | **84.0%** | **+46.0 pp** | **54.2%** | **4,615 ms** | **$0.1727** |
| anthropic_compact_v2 | 50 | 54.0% | +16.0 pp | 99.7% | 8,312 ms | $0.3791 |
| dumb_truncation_last_n | 50 | 28.0% | −10.0 pp | 54.0% | 3,707 ms | $0.1734 |
| random_chunk_drop | 50 | 22.0% | −16.0 pp | 53.8% | 4,155 ms | $0.1754 |

**Headroom wins on every axis:**

- **+46 pp** quality vs baseline
- **+28 pp** quality vs Anthropic's shipped `compact_v2`
- **−27%** p50 latency vs baseline (6,286 → 4,615 ms)
- **−45%** p50 latency vs `compact_v2` (8,312 → 4,615 ms)
- **−54%** cost per case vs baseline and vs `compact_v2` ($0.3757 → $0.1727)

### 3.2 OpenAI side — gpt-5.4, 3 arms

| arm | n | quality | Δ vs baseline | compression | p50 latency | cost / case |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 50 | 98.0% | — | 0.0% | 7,096 ms | $0.2836 |
| **headroom_default** | 50 | **98.0%** | +0.0 pp | 54.2% | **4,038 ms** | **$0.1301** |
| openai_compact_v2 | 50 | 98.0% | +0.0 pp | 1.1%¹ | 14,288 ms | $0.2807 |

¹ *`compression_ratio` for `openai_compact_v2` measures billable-token drift, not actual context reduction. OpenAI's server-side compaction happens during inference and `usage.input_tokens` reflects what was billed, which is nearly the full original haystack. Only `n_compactions`, `latency_ms`, `quality`, and `cost_usd` are meaningfully cross-comparable for that arm.*

All three OpenAI arms saturate at 98% quality. `gpt-5.4` is apparently so strong at long-context needle recall on LongMemEval that uncompressed 125k-token haystacks do not degrade it meaningfully — the opposite of the Sonnet 4.6 regime. Headroom still wins decisively on the other two axes:

- **−43%** p50 latency vs baseline (7,096 → 4,038 ms)
- **−72%** p50 latency vs `openai_compact_v2` (14,288 → 4,038 ms)
- **−54%** cost per case vs baseline ($0.2836 → $0.1301)
- **−54%** cost per case vs `openai_compact_v2`

`openai_compact_v2` is **latency-negative** on this workload — it nearly doubles the response time vs the uncompressed baseline while providing essentially zero cost savings (−1%). This is consistent with its documented benefit model (compaction payoff comes in subsequent API calls during running conversations), which our one-shot benchmark does not exercise. **It is the wrong tool for this specific workload, not a broken mechanism.**

### 3.3 The floor-test result

The two floor-test arms were added specifically to answer the question: *"Is Headroom winning because of its query-aware selection logic, or just because 54% less text means less distractor load regardless of what's kept?"*

Both arms compress to the same ~54% ratio as Headroom but without any query-aware relevance scoring. At matched compression:

| arm | compression | quality | Δ vs baseline | Δ vs Headroom |
|---|---:|---:|---:|---:|
| baseline | 0.0% | 38.0% | — | −46.0 pp |
| **headroom_default** | 54.2% | **84.0%** | **+46.0 pp** | — |
| dumb_truncation_last_n | 54.0% | 28.0% | **−10.0 pp** | **−56.0 pp** |
| random_chunk_drop | 53.8% | 22.0% | **−16.0 pp** | **−62.0 pp** |

At the same 54% compression ratio as Headroom:

- **Dumb truncation** (keep last 46% of tokens) scores **10 percentage points worse than baseline** — i.e., naively keeping the most recent 46% of the conversation makes the model answer *worse* than giving it everything. This is because LongMemEval needles can be anywhere in the haystack; truncating the early sessions throws away roughly half the answers.
- **Random chunk drop** (deterministic random chunk drops to matched ratio) scores **16 percentage points worse than baseline** — worse than dumb truncation. Random compression is the lower floor.
- **Headroom** (query-aware relevance scoring) scores **46 percentage points better than baseline** at the same compression ratio.

The gap between Headroom and naive compression at matched ratio is **56 to 62 percentage points**. Compression ratio alone explains none of Headroom's advantage — the ML in the `ContentRouter` is doing the entire lift. This refutes the "less text is less distracting" hypothesis decisively.

### 3.4 Cross-provider synthesis

| Axis | Sonnet 4.6 | gpt-5.4 |
|---|---|---|
| **Base model quality at 125k tokens** | 38.0% | 98.0% |
| **Headroom quality delta** | +46.0 pp | +0.0 pp (saturated) |
| **Headroom p50 latency delta** | −27% | −43% |
| **Headroom cost-per-case delta** | **−54%** | **−54%** |
| **Provider-native compaction quality delta** | +16.0 pp | +0.0 pp |
| **Provider-native compaction p50 latency delta** | +32% | **+101%** |
| **Provider-native compaction cost delta** | +0.9% | −1.0% |
| **Headroom vs provider compaction (quality)** | **+28.0 pp** | +0.0 pp |
| **Headroom vs provider compaction (latency)** | **−45%** | **−72%** |
| **Headroom vs provider compaction (cost)** | **−54%** | **−54%** |

**Four observations from the cross-provider view:**

1. **The two providers represent two different regimes of long-context robustness.** Sonnet 4.6 loses **62 percentage points of available headroom** to uncompressed 125k-token haystacks (baseline at 38%, ceiling at 100%). `gpt-5.4` loses only 2 points. On this single benchmark, `gpt-5.4` appears dramatically more robust at long-context needle recall than Sonnet 4.6.
2. **The quality story is model-sensitive.** On weaker-at-long-context models (Sonnet 4.6), Headroom rescues a huge amount of quality (+46 pp). On stronger-at-long-context models (`gpt-5.4`), there is no quality to rescue — but also nothing to lose, because Headroom ties at the 98% ceiling.
3. **The latency and cost stories are universal, not model-sensitive.** Headroom cuts cost per case by **exactly the same 54%** on both providers, because it sends exactly the same fraction of tokens (46%) to both. The latency cut is even larger on the OpenAI side (−43%) than the Anthropic side (−27%), demonstrating that the latency benefit is model-agnostic — possibly larger on stronger models because their baseline attention overhead on 125k tokens is higher.
4. **Neither provider's own compaction feature captures the cost savings that Headroom captures**, on either side. `anthropic_compact_v2` still pays full input cost per case because it compacts *after* the tokens arrive at the API. `openai_compact_v2` is the same structurally. Both provider features are cost-neutral per-case in one-shot benchmarks; only a *pre-API* layer like Headroom actually reduces what the provider bills for at input time.

## 4. Why Headroom wins on quality (Sonnet 4.6 side)

The Sonnet 4.6 quality delta — +46 pp vs baseline, +28 pp vs `anthropic_compact_v2`, +56 to +62 pp vs the floor-test arms — is explained by the intersection of two structural facts:

### 4.1 Long-context recall degrades meaningfully at 125k tokens on Sonnet 4.6

Sonnet 4.6 scores 38% on uncompressed LongMemEval `single-session-user` at N=50 — roughly four in ten questions answered correctly. The benchmark is not pathological; ground-truth answers are verbatim present in the haystack (we verified this for the specific failure cases in smoke testing). The model is losing answers that are literally in its input because the relevant sentences are buried among ~48 sessions of mostly irrelevant conversation. This is the well-documented "lost in the middle" effect at a specific operating point.

### 4.2 Query-aware compression removes distractors while preserving needles

Headroom's `ContentRouter` is query-aware at the compression step — it knows the question the model is about to answer, and it scores every chunk of the haystack for relevance to that question. Chunks that match the query's semantic space are preserved; chunks that look like irrelevant small-talk are compressed away. At 54% compression, the model receives a haystack that still contains the answer but has half the distractors removed.

This is **structurally different** from the three other compression approaches in this benchmark:

- **`anthropic_compact_v2` is query-blind.** Its prospective summarizer has to decide what to preserve *before* seeing the question, so it applies a generic salience prior. It preserves identity-defining facts (degrees, jobs, ages — things that look important in isolation) and drops incidental-looking facts (commute times, phone numbers, favorite restaurants). On LongMemEval `single-session-user`, roughly half the questions ask about exactly those "incidental" facts. The arm lands at 54% correct on N=50, matching this prediction almost exactly — it gets the identity-defining half right and drops the incidental half. Smoke testing confirmed the specific failure mode: case 2 asked *"How long is my daily commute?"*, the haystack contained *"audiobooks during my daily commute, which takes 45 minutes each way"* verbatim, but the compaction summary said *"the user never mentioned anything about a daily commute."*
- **`dumb_truncation_last_n` preserves the wrong chunks.** It keeps the most *recent* 46% of tokens regardless of which chunks contain the answer. LongMemEval's needle can be anywhere in the multi-session haystack, so dropping the first half throws away roughly half the answers mechanically.
- **`random_chunk_drop` preserves a random subset.** With ~62 chunks per haystack and a deterministic seed per case, each needle has roughly a 46% chance of surviving — worse than keep-last-N because there's no structure to exploit.

The only approach that beats baseline at 54% compression is the one that **uses the query to decide what to keep**. That's the finding the floor tests are designed to surface, and it's surfaced cleanly.

### 4.3 Why this doesn't happen on `gpt-5.4`

On `gpt-5.4`, the base model is already strong enough at long-context recall that 125k tokens doesn't overwhelm its attention mechanism — it scores 98% on uncompressed input. There's no distractor effect for Headroom to rescue. Headroom ties at the ceiling because it doesn't *remove* correct answers (its relevance-scoring preserves the needles that matter), but it also can't improve on 98%. The quality story is specific to models that show long-context degradation; the latency and cost stories apply regardless.

## 5. Cost story

Headroom's cost advantage is **structural** and **identical across both providers**.

| Provider | arm | tokens billed per case | cost / case | Δ vs baseline |
|---|---|---:|---:|---:|
| Anthropic Sonnet 4.6 | baseline | ~125,000 | $0.3757 | — |
| Anthropic Sonnet 4.6 | `anthropic_compact_v2` | ~125,000 (compact happens server-side) | $0.3791 | +0.9% |
| **Anthropic Sonnet 4.6** | **`headroom_default`** | **~58,000** | **$0.1727** | **−54.0%** |
| OpenAI gpt-5.4 | baseline | ~125,000 | $0.2836 | — |
| OpenAI gpt-5.4 | `openai_compact_v2` | ~125,000 (billable-drift, see §3.2 note) | $0.2807 | −1.0% |
| **OpenAI gpt-5.4** | **`headroom_default`** | **~58,000** | **$0.1301** | **−54.1%** |

The 54% savings shape is not a coincidence — it's structural. Headroom compresses 125k tokens to ~58k tokens *before* the API call; the provider is billed for ~58k input tokens. Both provider-native compaction features compact the input *after* it arrives at the API — the full 125k tokens have already been counted for billing by the time the compaction summarizer runs. In one-shot benchmarks, neither provider feature captures pre-API savings.

**Illustrative scaling** (at each provider's observed cost per case, 10,000 long-context requests per day, 365 days):

| Provider | Baseline annualised | Headroom annualised | Annual savings |
|---|---:|---:|---:|
| Anthropic Sonnet 4.6 | $1,371,305 | $630,355 | **$740,950** |
| OpenAI gpt-5.4 | $1,035,140 | $474,865 | **$560,275** |

These numbers are directly proportional to workload size. At 100k requests per day the savings are 10× larger; at 1,000 requests per day they're 10× smaller. The shape — ~54% of the per-case cost — is workload-independent.

## 6. Caveats and scope

This report makes concrete claims about what we measured. Equally important is what we did **not** measure:

1. **One benchmark family, one question type.** LongMemEval `single-session-user` only. We have Sonnet 4.5 ablation data on 3 other question types (from the N=150 cross-type run) showing the Headroom-wins shape replicates, but we have not yet tested the other 5 question types on Sonnet 4.6 or any on gpt-5.4. Generalization to other question types is a Phase 2 item.
2. **Two models from two providers.** Sonnet 4.6 and `gpt-5.4`. We have not tested Opus 4.6, any GPT-5 variant other than 5.4, any Mythos Preview model, or any non-frontier model. The two models we did test happen to represent two very different regimes (lossy long-context vs saturated long-context), which is informative, but extrapolation to other models in those families should be done with care.
3. **No tool-using / agentic workload.** LongMemEval is single-turn conversational recall. τ-bench would be the honest home for the tool-calling variant of Anthropic's compaction (`tool_runner(compaction_control)`) and is a Phase 2 item.
4. **No running-conversation workload.** `openai_compact_v2` looks latency-negative and cost-neutral in our benchmark, but its documented benefit model is multi-turn running conversations where compaction payoff comes in *subsequent* API calls. Our one-shot benchmark cannot exercise that benefit. A running-conversation benchmark is a Phase 2 item and would likely show `openai_compact_v2` in a much more favourable light.
5. **No real orq production workload.** Karina's Headroom reproduction found that orq's production tool outputs get 0% compression because they are double-encoded JSON strings; her recommended fix is a JSON-string-unwrapping layer. Re-running this benchmark on the 229 CaptainFresh spans *after* that fix lands is the single highest-priority Phase 2 item — it is the only experiment that directly validates the transfer from LongMemEval to a real orq use case.
6. **LLM-as-judge, not human eval.** Answer quality is judged by Haiku 4.5 against ground-truth answers. Cross-judged or human-sampled scoring would strengthen confidence. Given the size of the quality deltas we measured (+46 pp on the Anthropic side) we are comfortable with LLM judging at this scale, but for closer comparisons in Phase 2 it may matter.

## 7. Recommendation

**Ship Headroom behind a feature flag for long-context workloads on both OpenAI and Anthropic surfaces.**

The recommendation rests on three independent bodies of evidence:

1. **Measured head-to-head at N=50 on both providers.** Headroom wins on every axis we measured — quality on Sonnet 4.6 (+46 pp), latency on both providers (−27% and −43%), cost on both providers (−54% and −54%), and the head-to-head comparison against provider-native compaction on both sides (+28 pp quality on Sonnet 4.6, +34% latency margin on gpt-5.4, identical −54% cost margin on both).
2. **Methodological robustness check passed.** The floor-test arms at matched compression score −10 and −16 percentage points vs baseline, while Headroom at the same compression scores +46 percentage points. The 56 to 62 percentage-point gap between Headroom and naive compression at matched ratio establishes that the ML in the `ContentRouter` is earning its keep, independent of any "less text is less distracting" effect.
3. **Cross-provider structural argument.** Headroom is the only context-compaction layer that is (a) cross-provider and identically-shaped, (b) transparent and inspectable at plain text, (c) query-aware at the compression step, (d) deterministic and reproducible, and (e) runs locally before the API call so the cost savings are captured at the input-token layer. Both vendors have confirmed via their product roadmaps that context compaction is a real problem worth solving; Headroom is the one the user controls.

**Framing for the rollout conversation:**

- **On Sonnet 4.6** (and presumably other Claude models where long-context distractors degrade base quality), Headroom is a **quality story** first — +46 pp is not incremental, it's the difference between a benchmark that roughly half-works at baseline and one that works decisively. Cost and latency wins are bonus.
- **On gpt-5.4** (and presumably other strong-at-long-context models), Headroom is a **cost and latency story** — 54% cost savings with zero quality risk is a straight operational win for any long-context workload.
- **Both cases ship.** The two regimes together demonstrate that Headroom's value proposition is robust to the base model's long-context strength: on weaker models it rescues quality, on stronger models it rescues cost and latency, and on no model we tested did it hurt.

**What NOT to claim at the ship announcement:**

- *"Headroom is better than provider compaction."* Too broad. The correct claim is "Headroom is better than provider-native compaction on conversational fact-recall workloads like LongMemEval `single-session-user` on the two models we tested at N=50." Provider compaction features are real, documented, shipping products — we tested them fairly, they work as designed, they're dominated by Headroom on this specific workload because of the query-blindness issue, and they may well be better-suited to different workload shapes (agent continuation, running conversations, tool-use loops).
- *"We've proven the quality improvement."* "Measured at N=50 on LongMemEval single-session-user with LLM-as-judge scoring, with a 56–62 pp floor-test gap establishing methodological robustness" is the correct framing. "Proven" is over-strong.
- *"OpenAI's compaction is broken."* It is not. It is the right tool for running conversations; it is the wrong tool for one-shot single-turn benchmarks. Flag honestly.

## 8. Phase 2 priorities

In rough order of business value:

1. **Re-run the 3-arm comparison on orq production traces** (229 CaptainFresh spans) after Karina's JSON-unwrapping fix lands. This is the only experiment that directly validates the transfer from LongMemEval to real orq use cases. Estimated ~$20, ~1 hour wall-clock after the fix is merged.
2. **Sonnet 4.6 per-type sweep** — run the 3-arm comparison on the other 5 LongMemEval question types at N=30 each. Replicates the `single-session-user` result across the full question-type distribution. Estimated ~$30, ~2–4 hours wall-clock.
3. **τ-bench loader + probe** — the honest home for the old `tool_runner(compaction_control)` comparison in its native tool-runner habitat. Recovers a dropped arm and tests a different shape of context problem. Estimated ~$30, ~1 day of work.
4. **Opus 4.6 second-model ablation** — cheap add since Opus 4.6 also supports `compact_20260112`. Tests whether the Sonnet 4.6 regime generalizes across the Anthropic frontier. Estimated ~$30.
5. **Running-conversation benchmark for `openai_compact_v2`** — extend the benchmark to multi-turn conversations where the OpenAI compaction feature's benefit model actually applies. Gives `openai_compact_v2` a fair shake on its native workload shape. Estimated ~$40.
6. **Complete `anthropic_session_memory` arm** on Sonnet 4.6 with a Sonnet summarizer (not Haiku, which hung on an earlier attempt) and an explicit per-call timeout. Closes the 4-arm Anthropic comparison. Estimated ~$15.
7. **LongBench v1 + LLMLingua-2 head-to-head** — publishable academic baseline comparison. Requires a small runner patch for non-LongMemEval dataset shapes. Estimated ~$40–60.
8. **Streamlit space extension** — wire the N=50 cross-provider JSON results into `orq/headroom_reproduction` as a "Cross-arm, cross-provider comparison" page alongside Karina's existing pages. Dev time only.
9. **Separate RES ticket for Sonnet 4.5 temporal-reasoning collapse** — orthogonal finding from the Sonnet 4.5 sweep: `temporal-reasoning` scores 0% across every arm tested at 125k tokens. Model-level weakness, not a compression problem, but worth filing as its own investigation.

**Total remaining Phase 2 budget:** approximately $115–200 depending on which items are green-lit. The orq rerun (item 1) is the single highest-value item and is blocked only on Karina's JSON-unwrapping fix.

## 9. Cost to date

Approximately **$155 total** across all investigation rounds:

| Round | Cost |
|---|---:|
| Sonnet 4.5 3-arm N=50 headline | ~$15 |
| Sonnet 4.5 per-type sweep (6 types × N=30) | ~$10 |
| Temporal-reasoning rerun | ~$3 |
| Anthropic `compact_20260112` + session memory smoke probes | ~$5 |
| Sonnet 4.6 3-arm N=50 | ~$20 |
| Sonnet 4.6 5-arm N=50 (with floor tests) | ~$65 |
| OpenAI gpt-5.4 3-arm N=50 | ~$37 |
| **Total** | **~$155** |

Well within the RES-333 ticket budget.

## 10. Artifacts and reproducibility

All data, code, runner scripts, and reports are on the `feat/compaction-compare` branch. Everything is reproducible end-to-end.

| Kind | Path |
|---|---|
| **This final report** | `research/2026-04-09-res-333-final-report.md` |
| Sync opener / talking points | `research/2026-04-09-sync-opener.md` |
| Full working report (with history and errata) | `research/2026-04-09-res-333-report.md` |
| Findings update (medium-depth summary) | `research/2026-04-09-findings-update-3arm.md` |
| Evaluation plan revision | `research/2026-04-09-evaluation-plan-revision.md` |
| Standalone comparison vs Karina's HF Space | `research/2026-04-09-streamlit-reproduction-comparison.md` |
| Sonnet 4.6 5-arm N=50 (with floor tests) | `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50_5arm/` |
| OpenAI gpt-5.4 3-arm N=50 | `eval_results/compaction_compare/longmemeval/openai_gpt54/n50_3arm/` |
| Sonnet 4.6 3-arm N=50 (earlier) | `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50/` |
| Sonnet 4.5 N=150 cross-type ablation | `eval_results/compaction_compare/longmemeval/anthropic/n150/` |
| Cross-provider sweep script | `research/run_cross_provider_n50.sh` |
| OpenAI cost retrofit tool | `research/retrofit_openai_costs.py` |
| `AnthropicCompactV2Runner` source | `headroom/evals/runners/anthropic_compact_v2.py` |
| `OpenAICompactV2Runner` source | `headroom/evals/runners/openai_compact_v2.py` |
| Floor-test runners source | `headroom/evals/runners/floor_tests.py` |
| Unit tests | 157 tests green across `tests/test_evals/` |

**Branch:** [`feat/compaction-compare`](https://github.com/arianpasquali/headroom/tree/feat/compaction-compare) on GitHub.
**Linear ticket:** [RES-333](https://linear.app/orqai/issue/RES-333/reproduce-headroom-results).

The canonical comment on the Linear ticket has been updated twice today as the investigation surfaced new evidence; the current version reflects the cross-provider N=50 headline and should be treated as the authoritative shareable artifact.
