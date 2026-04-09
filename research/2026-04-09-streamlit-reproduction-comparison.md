# Compaction-Compare vs `orq/headroom_reproduction` HF Space

**Date:** 2026-04-09
**Author:** Arian Pasquali
**Scope:** Standalone comparison of the two Headroom evaluation workstreams — Karina's HF Space reproduction (`orq/headroom_reproduction`) and this branch's cross-arm compaction-compare experiment on LongMemEval (`feat/compaction-compare`).
**Purpose:** Reconcile the two efforts so the team can read them as one coherent picture before the RES-333 sync.

Companion to the full RES-333 report at [`research/2026-04-09-res-333-report.md`](./2026-04-09-res-333-report.md). This file is deliberately scoped to *just* the comparison — pull the main report for full methodology, caveats, and recommendations.

> ⚠ **See also:** [`research/2026-04-09-evaluation-plan-revision.md`](./2026-04-09-evaluation-plan-revision.md) — evaluation plan correction triggered by the discovery of Anthropic's `compact_20260112` server-side feature and the session memory cookbook pattern, both of which post-date our SDK and were missed in the original cross-arm investigation. Neither affects Karina's reproduction comparison directly (her work was Headroom-only), but they change how the "what we learned that the reproduction doesn't cover" section in §4 should be read — specifically §4.1 "Provider compaction doesn't exist" is half-wrong for Anthropic.

---

## 1. What the Streamlit reproduction does

Five pages, all Headroom-only (no cross-arm comparison):

1. **Headroom Benchmarks** — 1:1 reproduction of the README: needle-in-haystack (100 logs, 1 CRITICAL error at pos 67 → checks for `PG-5523`), 4 workload scenarios (code search, SRE debugging, GitHub issue triage), plus the published accuracy table.
2. **Parameter Study** — interactive sweep across `max_items_after_crush`, `min_ratio_relaxed / aggressive`, `model_limit`, `bias`.
3. **orq Dataset** — 229 real orq.ai production traces (CaptainFresh M&A due diligence agent, 46–191k prompt tokens per span). Compression, cost projection, per-span latency, net-latency analysis (`tokens_saved × 0.05 ms/token − compression_overhead`), and a Claude-powered in-app explainer.
4. **LoCoMo Eval** — 10 long multi-session conversations (400–680 turns each). Context-window sweep `{1k, 2k, 4k, 8k, 16k, Full}`, QA accuracy by category (single-hop, temporal, multi-hop, open-ended, adversarial-excluded), semantic-diff "what was lost" view.
5. **Conclusion** — parameter recommendations, accuracy thresholds, latency tables, orq-specific architectural fix, priorities for orq.ai.

The headline LoCoMo curve:

| Context | Compression | QA accuracy | Verdict |
|---|---:|---:|---|
| Full | 0% | 88% | Baseline |
| 16k | 35% | 82% | Minimal loss |
| 8k | **67%** | **71%** | Recommended max |
| 4k | 84% | 58% | Significant loss |
| 2k | 92% | 43% | Severe |
| 1k | 96% | 29% | Only recent survives |

**Key reproduction findings:**

- Parameters that matter most: `max_items_after_crush` (10–15 recommended), `min_ratio_relaxed/aggressive`, `model_limit`.
- Pipeline overhead 5–50 ms per span; LLM time saved (at ~0.05 ms/token for Sonnet) exceeds overhead by 2–10×.
- **orq-specific blocker:** orq tool outputs arrive as double-encoded JSON strings → `ContentRouter` gets 0% compression on them → a JSON string unwrapping layer before the router would unlock 30–44% compression. 57.5% of orq tool messages contain compressible nested arrays; 53% of tool content lives in those arrays.
- Priorities for orq.ai: (1) JSON unwrapping, (2) enable CCR for exact figure retrieval, (3) keep `max_items` at 10–15, (4) A/B accuracy tests on real agent outputs, (5) test coding & other workload types.

**Quality measurement.** Karina uses a regex/keyword match (`_answer_found`) — an answer is "preserved" if more than half of its significant words still appear in the compressed text. No LLM answer call, no LLM judge.

```python
def _answer_found(answer, text):
    ...
    return found_count >= max(1, len(a_words) // 2)
```

---

## 2. What we confirmed

| Reproduction finding | Our evidence |
|---|---|
| Headroom compression actually works (~55% on real workloads) | ✅ Matches — **54.3% on LongMemEval headline**, 54.7–55.8% stable across all 6 question types |
| Pipeline overhead is a net latency win | ✅ Stronger — p50 latency drops from **7.1 s (baseline) to 4.4 s (Headroom)** at ~110k tokens. −38%, replicates across every question type |
| Critical / high-information items are preserved | ✅ Matches — Headroom beat or matched baseline on 5 of 6 LongMemEval question types at 54% compression |
| The LoCoMo 67% compression / 71% accuracy anchor | ✅ Cited as-is; not re-run. Served as our starting reference for the N=50 design |
| Compression preserves answer findability on conversational data | ✅ Matches — `summary_prompt` is neutral on `single-session-user` (±2pp), Headroom is net positive |

---

## 3. What we learned differently (same direction, stronger claim)

### 3.1 At long context, compression *improves* quality — it doesn't just preserve it

Karina's LoCoMo curve is monotonically decreasing: more compression → less accuracy. Every data point loses something versus the uncompressed baseline. Our LongMemEval numbers are **monotonically inverted at the 54% compression point** on 5 of 6 question types:

| Question type | baseline | headroom | Δ |
|---|---:|---:|---:|
| single-session-assistant | 56.7% | **93.3%** | **+36.7** |
| single-session-preference | 10.0% | 33.3% | +23.3 |
| knowledge-update | 46.7% | 70.0% | +23.3 |
| single-session-user (headline) | 52.0% | 74.0% | +22.0 |
| multi-session | 16.7% | 30.0% | +13.3 |
| temporal-reasoning (rerun) | 0.0% | 6.7% | +6.7 (noise) |

*Note on temporal-reasoning:* a clean rerun (Apr 9 13:46, with the rate-limit retry code) confirmed baseline=0.0% at full N=30 and showed the 6.7% Headroom "win" is stochastic — the 2/30 correctly-answered questions flipped identity between the original run (summary_prompt) and the rerun (Headroom). See the main RES-333 report §5.3 for the full analysis.

**This doesn't contradict Karina — it extends her finding.** LoCoMo tops out at ~21k tokens (full conversation), which is why it failed our token-length gate in the first place. At 21k tokens Sonnet 4.5 is comfortably inside its attention budget, so compression is a pure tradeoff. At ~110k tokens LongMemEval pushes past the "lost in the middle" threshold and removing distractors becomes a **net quality win**. The LongMemEval paper's own finding that some memory systems beat oracle full-context retrieval generalises directly to in-context compression once the haystack is long enough.

### 3.2 Latency evidence scales up

Karina estimated LLM time saved at ~0.05 ms/token (from Sonnet's ~20k tok/s input throughput) and showed 5–50 ms pipeline overhead → 500–1,300 ms estimated LLM savings. We measured the real end-to-end wall-clock difference on actual API calls at ~110k tokens: **2,725 ms median savings per call** (7,100 ms → 4,375 ms). Roughly 2× her projected per-call savings, which fits — her model was on conversations 5× smaller, and the "lost in the middle" model-time gradient is non-linear.

### 3.3 "Temporal drops first" holds at scale — and gets worse

On LoCoMo, "Temporal" was the category that dropped first at low context limits. On LongMemEval at ~110k we see the terminal form of that failure: **baseline is 0% across the full clean rerun of N=30**, and Headroom and summary_prompt hover at 0–7% depending on which 2 of 30 questions happen to get the stochastic right answer. No arm has a real signal. Sonnet 4.5 at 110k tokens cannot do time arithmetic over haystack sessions. It is not a compression problem; it is a Sonnet-4.5-at-long-context problem. Worth its own RES ticket.

### 3.4 The "accuracy threshold" is question-type dependent

Karina's headline takeaway is "compress up to ~67% to keep accuracy ≥71%". That's a useful single number on LoCoMo. Our per-type breakdown shows the real shape is **per-question-type**: at a single 54% compression point, `single-session-assistant` gains +36.7pp while `multi-session` only gains +13.3pp. A single-number accuracy threshold undersells the interaction between compression and question semantics. The parameter defaults she recommends (`max_items` 10–15, `model_limit` matching the real model) are unchanged by our work.

---

## 4. What we learned that the reproduction doesn't cover

These are genuine new findings, not extensions.

### 4.1 Provider compaction landscape — what the Apr 8 probe missed, and the 2026-04-09 correction

Karina's reproduction is Headroom-only. We took RES-333's literal framing ("compare with openai compaction, anthropic compaction") and tried to build the comparison, which forced us to read the provider SDKs. The initial survey on Apr 8 found:

- **Anthropic `messages.create(context_management={clear_tool_uses, clear_thinking})`**: lossy block clearing — no-op on LongMemEval (no tool uses, no thinking turns).
- **Anthropic `beta.messages.tool_runner(compaction_control=...)`**: summarization, but **only fires inside tool-runner iterations**. Forcing it onto a non-tool benchmark requires dummy-tool scaffolding that distorts both tokens and behavior (our smoke run hung for 22 minutes on pydantic validation errors from the model mis-calling dummy tools).
- **OpenAI `responses.create(truncation="auto")`**: lossy first-N drop, only fires when input exceeds the context window. With gpt-4o-mini's 128k window and LongMemEval at ~104k, it never fires.
- **OpenAI `responses.compact()`** (probe on `gpt-4o-mini`): the `CompactedResponse` it returned had no assistant output and its `id` was not chainable (`400 previous_response_not_found` when used as `previous_response_id`), so we initially characterised it as an analytics-only endpoint.

From that, the report previously concluded "Neither provider ships summarization-based compaction at the standard API level for non-tool-using benchmarks." **That conclusion was wrong on both sides, for two different reasons, and is corrected below.**

#### 4.1.a Anthropic — `compact_20260112` is a real primitive on Sonnet 4.6+

While building out the benchmark we found that Anthropic *does* ship a first-class compaction primitive — the `context_management.edits=[{"type": "compact_20260112", ...}]` parameter on `beta.messages.create`, gated on a `compact-2026-01-12` beta header and supported on Sonnet 4.6 / Opus 4.6 / Mythos Preview (explicitly **not** on Sonnet 4.5, which is why the first probe against Sonnet 4.5 saw nothing fire). It is server-side, automatic at a configurable `input_tokens` threshold, works on plain `messages.create` with no tool_runner required, and returns a `compaction` content block that the caller passes back in the next request. It is lossy summarization with a customisable `instructions` hook.

This is wired up in the benchmark as the `anthropic_compact_v2` arm (`headroom/evals/runners/anthropic_compact_v2.py`). The runner ships with a role-disambiguation system prompt and third-person compaction instructions to work around a LongMemEval-specific role-confusion failure mode documented in the runner's module docstring.

#### 4.1.b OpenAI — the Apr 8 "analytics endpoint" finding was a model-gating artefact

On Apr 9, a re-read of the current [OpenAI Compaction guide](https://developers.openai.com/api/docs/guides/compaction) revealed that OpenAI *also* ships server-side context compaction in the Responses API — directly contradicting the Apr 8 "analytics endpoint" conclusion. The guide shows this literal Python example:

```python
response = client.responses.create(
    model="gpt-5.3-codex",
    input=conversation,
    store=False,
    context_management=[{"type": "compaction", "compact_threshold": 200000}],
)
```

The feature surfaces as a **list** of edit descriptors (verified against the server: sending a single object returns `400 "expected an array of objects"`), plus a standalone `POST /responses/compact` for explicit control. The returned compaction item **is** chainable (append to the next `input` array, or pass via `previous_response_id`), and the docs explicitly state *"do not prune /responses/compact output. The returned window is the canonical next context window"*.

The most likely explanation for the Apr 8 finding is **model gating**: the probe ran against `gpt-4o-mini`, while the guide's examples use `gpt-5.3-codex` (for automatic `context_management`) and `gpt-5.4` (for the standalone `responses.compact()` call). The guide notes *"The latest models are trained to analyze prior conversation state and produce a compaction item..."* — a gpt-4o-mini probe would return a degenerate analytics-only response even though the endpoint exists, because the underlying model isn't trained to produce real compaction items.

**SDK version caveat.** The published `openai==2.15.0` Python SDK does NOT yet expose `context_management` as a typed parameter on `responses.create()` — passing it as a direct kwarg raises `got an unexpected keyword argument 'context_management'` from the SDK's Pydantic layer before any HTTP round-trip. The `ResponseCompactParams` typed literal for the standalone `/responses/compact` endpoint *is* in the SDK but tops out at `gpt-5.2-pro` — `gpt-5.3-codex` and `gpt-5.4` are not in the type list. This means the SDK is **strictly stale versus the live API**: the docs reference models and parameters the typed interface hasn't caught up with. Our `openai_compact_v2` runner therefore passes `context_management` through the SDK's documented `extra_body` escape hatch and relies on the model-name `Union[Literal[...], str, None]` fallback to forward the new model strings to the server. When a future SDK release adds a typed `context_management` field, we can switch to the direct kwarg and update the test assertions in lockstep.

Semantic difference worth flagging for the sync: Anthropic's compaction block is a natural-language summary the caller can read, audit, or even edit; OpenAI's compaction item is **opaque and encrypted**, "not intended to be human-interpretable." For failure analysis and reporting "what got dropped," Anthropic's output is introspectable while OpenAI's is not.

This is now wired up in the benchmark as the `openai_compact_v2` arm (`headroom/evals/runners/openai_compact_v2.py`), mirroring the Anthropic v2 runner's shape so the two can be compared apples-to-apples. Iteration status as of 2026-04-09:

1. ✅ CLI + driver + config + dispatch + 10 unit tests green against fake clients.
2. ✅ Wire shape corrected to `context_management=[{"type": "compaction", "compact_threshold": N}]` after probing the real server (layer-2 error: "expected an array of objects").
3. ✅ Real-API smoke against `gpt-5.4` on 2 LongMemEval cases succeeded end-to-end: `n_success=2 n_errors=0 n_compactions=1 mean_latency_ms=19354`.

#### 4.1.b.i Smoke findings — two surprises worth a follow-up

The 2026-04-09 smoke (`/tmp/cc_smoke_openai_compact_v2`) surfaced two things that materially change what we should report at the RES-333 sync.

**Surprise 1 — both answers correct, including the commute case.** On `longmemeval_e47becba` ("What degree did I graduate with?") and `longmemeval_118b2229` ("How long is my daily commute?"), `openai_compact_v2` returned:

- Case 1: *"According to our prior conversation, you said you graduated with a degree in Business Administration"* ✅ (ground truth: Business Administration)
- Case 2: *"According to our prior conversation, you said your daily commute is 45 minutes each way"* ✅ (ground truth: 45 minutes each way)

Case 2 is specifically flagged in `anthropic_compact_v2.py`'s module docstring as the failure mode of prospective summarization:

> "case 2 ('How long is my daily commute?' — ground truth '45 minutes each way') still fails because the compaction summarizer is query-blind: it applies a generic salience prior that preserves identity-defining facts (degrees, jobs) but drops incidental-looking facts (commute times, favourite restaurants) even when they happen to be the later query target."

**`openai_compact_v2` answered the commute case correctly on the first try.** On n=2 this is suggestive, not conclusive — but it directly contradicts the "all prospective summarization is query-blind" framing we were about to put into the RES-333 report. The honest reading is: *OpenAI's and Anthropic's compaction implementations appear to use different salience priors, and on LongMemEval-style incidental-fact recall the OpenAI prior happens to hold up on a case the Anthropic prior doesn't.* A proper head-to-head at n≥20 on the same cases, with the judge enabled, is the blocking next step before anything stronger can be said. The new `compact_v2_headhead_smoke` helper in `research/run_compaction_compare_next.sh` runs both arms on the same 2 cases and is the fastest path to the n=20 version.

**Surprise 2 — we have no usable compression measurement for this arm.** The smoke reported `compression_ratio ≈ 0.01` even though `n_compactions == 1`. This is not a feature failure; it is a measurement gap. The OpenAI Responses API `ResponseUsage` type (openai 2.15.0) exposes only `input_tokens`, `input_tokens_details.cached_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`, and `total_tokens` — there is **no** field that reports post-compaction input tokens. `usage.input_tokens` is the billable count, which is what the caller sent, not what the model processed internally after the server's compaction pass.

Our runner computes `final_input_tokens = usage.input_tokens` and derives `compression_ratio` from it. For Anthropic's `compact_v2` this works because Anthropic's `BetaUsage.iterations[-1].input_tokens` reports the post-compaction iteration's input size. OpenAI exposes no equivalent. The runner docstring now documents this explicitly (`Compression-metric caveat` section in `headroom/evals/runners/openai_compact_v2.py`), and the inline computation site has a load-bearing comment warning readers not to cross-compare the field.

**Implications for the report tables.** In any cross-arm table that includes `openai_compact_v2`, the `compression_ratio` column for that row should be shown as `N/A`, or accompanied by a footnote stating "billable input drift — OpenAI Responses API does not expose post-compaction token counts; this number is not comparable to compression ratios for other arms." The three numbers that *are* cross-comparable for this arm are:

- `n_compactions` (did compaction fire? answers "yes" for gpt-5.4 at 60k threshold on ~110k haystacks)
- `latency_ms` (wall-clock cost of the compaction path, comparable to baseline and other arms)
- judge-scored answer quality (once the head-to-head is run with `--judge`)

**Follow-up ticket (not done today):** a paired-baseline measurement — run the same case twice, once with `context_management` and once without, and report compression as a latency or cost diff between the two. Doubles the cost per case but yields a real, cross-comparable number. Tracked separately; not a blocker for the RES-333 sync.

**Latency data point for the sync.** At ~110k haystack tokens, `openai_compact_v2` on gpt-5.4 ran at `p50 ≈ 19.3s` per case vs the Sonnet 4.5 baseline at `p50 ≈ 7.1s` from the n50 headline run. That is a **latency cost**, not a benefit, on this benchmark at this compaction threshold. It may reflect a larger model family, the compaction pass's own cost, or the first-call cold-path on a beta feature — but it is what we measured, and the report should say so.

Until the head-to-head n≥20 run completes, **any comparative claim between `anthropic_compact_v2` and `openai_compact_v2` should be footnoted "n=2 smoke"** and read as motivation, not conclusion.

#### 4.1.c Revised framing for Headroom's position

Both providers ship summarization-based compaction at the standard API level, on their latest models (Anthropic: Sonnet/Opus 4.6; OpenAI: GPT-5.3-codex / GPT-5.4). This **does not weaken** the case for Headroom — it strengthens a different claim:

> Headroom is the only cross-provider, transparent, question-aware, deterministic, inspectable context-compaction layer. Both vendors have now confirmed that context compaction is a real problem worth solving at the platform layer; Headroom is the one you control.

On the quality axis, our LongMemEval headline still stands: Headroom ships a **+22pp quality improvement** at 54% compression, while the vendor primitives aim primarily at cost/latency reduction rather than answer quality. A proper head-to-head at matched long-context lengths — `anthropic_compact_v2` (Sonnet 4.6) vs `openai_compact_v2` (GPT-5.4) vs `headroom_default` (either) — is the natural next experiment and will give RES-333 its cleanest cross-provider comparison yet.

### 4.2 Summary-prompt is schema-shaped

Feature A (Haiku 4.5 structured summary with `decisions / constraints / rejected_paths / file_refs / facts`) was tested in parallel with Headroom. It achieves ~40% compression cleanly but is **dominated or tied by Headroom on all 6 types**. The root cause we can identify: the schema is shaped for SWE/planning workloads, not for casual conversational recall ("what degree did I graduate with", "how long is my commute"). Karina's reproduction doesn't evaluate a summary-prompt alternative, so this is a new (negative) finding.

**Counter-nuance:** Feature A posts modest positive deltas on 4 of 6 types and a grand-mean Δ of +5.2pp. The technique itself is not a dead end — a schema redesign for conversational tasks is the obvious next experiment. (In the first run, Feature A appeared to be "the only arm clearing 0% on temporal-reasoning"; the rerun flipped that, showing the 6.7% was a 2/30 stochastic artefact rather than signal.)

### 4.3 End-to-end LLM-judged quality, not keyword presence

This is the biggest methodological delta between the two efforts. Karina's `_answer_found` measures **fact survival in the compressed representation** — whether more than half of the answer's significant words still appear in the compressed text. It does not answer whether an LLM, given that compressed input, actually *produces* the right answer.

We measure the latter: run Sonnet 4.5 on the compressed context, have Haiku 4.5 judge the output. A compressed context can contain the answer terms but still fail to elicit the right response (model gets distracted by remaining distractors), or conversely lack the exact answer phrasing but still elicit a correct inference.

**That's why our numbers and Karina's aren't directly comparable — they are measuring different quantities on different datasets.** Neither is wrong; they answer adjacent questions.

### 4.4 We have nothing on real orq traces — this is a gap

**This is the only gap the reproduction has and our work also has.** Karina found that orq's production tool outputs get **0% compression** because they're double-encoded JSON strings, and identified a JSON-string-unwrapping layer as the high-priority fix that would unlock 30–44% compression. We ran **zero** orq traces in the compaction-compare work. The +22pp quality gain on LongMemEval does **not** currently transfer to orq — we don't know whether, once unwrapping lands and orq JSON becomes compressible, the same "lost in the middle" quality-improvement effect would show up on M&A due diligence workloads.

**This should be Phase 2 workstream #1:** re-run the 3-arm comparison on the 229-span orq dataset after Karina's JSON-unwrapping fix lands.

---

## 5. What we did differently (methodology)

| Axis | Reproduction | compaction-compare |
|---|---|---|
| **Research question** | "Does Headroom's compression work and preserve quality on our workloads?" | "How does Headroom compare to provider compaction and a summary-prompt alternative at long context, end-to-end?" |
| **Arms** | Headroom only | baseline + `headroom_default` + `summary_prompt` (+ dropped `anthropic_compact`, `openai_compact`) |
| **Datasets** | LoCoMo (10 convs, 19–21k tokens), orq production (229 spans, 46–191k tokens), README-scenario reproductions | LongMemEval `s_cleaned` (N=50 headline + N=30 × 5 per-type; ~110k haystack tokens; 6 question types) |
| **Dataset gate** | None | Added "p50 ≥ 20k tokens" gate after self-review; rejected LoCoMo and Nemotron for this reason |
| **Quality signal** | Keyword / regex fact survival in compressed text (`_answer_found`) | End-to-end: Sonnet 4.5 answers from compressed context, Haiku 4.5 LLM-as-judge scores the answer |
| **Latency signal** | Pipeline overhead measured; LLM time saved estimated at 0.05 ms/token | Measured wall-clock end-to-end latency on real API calls |
| **Infrastructure** | Streamlit UI around existing `headroom` package | New `CompactionCompareDriver` + CLI subcommand + 3 HF loaders + 5 arm runners + Δ-quality report renderer + 106 unit tests |
| **Cost** | In-app compression + occasional Claude analysis calls | ~$15 total (smokes + N=50 headline + 5 per-type sweeps) |
| **Deliverable shape** | Interactive HF Space for exploration | Markdown + JSON reports, branch with commits, RES-333 report doc |
| **Output artefact** | `orq/headroom_reproduction` HF Space (publishable) | `feat/compaction-compare` branch + `research/2026-04-09-res-333-report.md` (internal) |
| **LoCoMo's role** | Primary benchmark surface with the full sweep | Appendix only — Karina's curve cited as supporting context, not re-run |

---

## 6. Implication for the sync

The two workstreams are **complementary and non-overlapping**:

- **Karina's reproduction** validates that Headroom's published claims hold on orq's own data, identifies the JSON-unwrapping fix as the highest-impact orq-specific unlock, and gives the team an interactive tool for exploring the parameter space.
- **compaction-compare** validates that Headroom wins against realistic alternatives at long context (where LoCoMo is too short to see it), surfaces the "compression *improves* quality past a context threshold" effect, and documents why provider-native compaction isn't a fair comparison baseline at the standard API level.

**Merging the two views into a one-paragraph meeting message:**

> Karina confirmed Headroom's technology claims on orq's own data. Our cross-arm comparison extends that to a long-context benchmark where Headroom **beats uncompressed baseline by 22pp and is 38% faster**, at 54% compression, across 5 of 6 LongMemEval question types. Provider-native compaction turned out not to exist at the standard API level for non-tool benchmarks — that's itself a RES-333 deliverable. Feature A is dominated by Headroom on 5/6 types with its current schema and should not ship as-is. The one gap spanning both efforts is: re-run our 3-arm comparison on the orq production dataset once Karina's JSON-unwrapping fix lands, to check whether the long-context quality improvement transfers to M&A due diligence.

---

## 7. Artifacts referenced

| Kind | Location |
|---|---|
| This comparison report | `research/2026-04-09-streamlit-reproduction-comparison.md` |
| Full RES-333 report | `research/2026-04-09-res-333-report.md` |
| Compaction-compare progress log | `research/2026-04-08-compaction-compare-progress.md` |
| Headline N=50 run (single-session-user) | `eval_results/compaction_compare/longmemeval/anthropic/n50/` |
| Per-type N=30 runs | `eval_results/compaction_compare/longmemeval/anthropic/by_type/<type>/` |
| Cross-type meta-report | `eval_results/compaction_compare/longmemeval/anthropic/cross_type_report.md` |
| HF Space (reproduction) | `orq/headroom_reproduction` on Hugging Face |
| HF Space source (offline) | `hf download orq/headroom_reproduction --repo-type space` |
| Branch | `feat/compaction-compare` |
