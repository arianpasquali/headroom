# Compaction-Compare vs `orq/headroom_reproduction` HF Space

**Date:** 2026-04-09
**Author:** Arian Pasquali
**Scope:** Standalone comparison of the two Headroom evaluation workstreams — Karina's HF Space reproduction (`orq/headroom_reproduction`) and this branch's cross-arm compaction-compare experiment on LongMemEval (`feat/compaction-compare`).
**Purpose:** Reconcile the two efforts so the team can read them as one coherent picture before the RES-333 sync.

Companion to the full RES-333 report at [`research/2026-04-09-res-333-report.md`](./2026-04-09-res-333-report.md). This file is deliberately scoped to *just* the comparison — pull the main report for full methodology, caveats, and recommendations.

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
| temporal-reasoning | 0.0% | 0.0% | 0.0 |

**This doesn't contradict Karina — it extends her finding.** LoCoMo tops out at ~21k tokens (full conversation), which is why it failed our token-length gate in the first place. At 21k tokens Sonnet 4.5 is comfortably inside its attention budget, so compression is a pure tradeoff. At ~110k tokens LongMemEval pushes past the "lost in the middle" threshold and removing distractors becomes a **net quality win**. The LongMemEval paper's own finding that some memory systems beat oracle full-context retrieval generalises directly to in-context compression once the haystack is long enough.

### 3.2 Latency evidence scales up

Karina estimated LLM time saved at ~0.05 ms/token (from Sonnet's ~20k tok/s input throughput) and showed 5–50 ms pipeline overhead → 500–1,300 ms estimated LLM savings. We measured the real end-to-end wall-clock difference on actual API calls at ~110k tokens: **2,725 ms median savings per call** (7,100 ms → 4,375 ms). Roughly 2× her projected per-call savings, which fits — her model was on conversations 5× smaller, and the "lost in the middle" model-time gradient is non-linear.

### 3.3 "Temporal drops first" holds at scale — and gets worse

On LoCoMo, "Temporal" was the category that dropped first at low context limits. On LongMemEval at ~110k we see the terminal form of that failure: `temporal-reasoning` is 0% across **both** baseline *and* Headroom. Sonnet 4.5 at 110k tokens cannot do time arithmetic over haystack sessions. It is not a compression problem; it is a Sonnet-4.5-at-long-context problem. Worth its own RES ticket.

### 3.4 The "accuracy threshold" is question-type dependent

Karina's headline takeaway is "compress up to ~67% to keep accuracy ≥71%". That's a useful single number on LoCoMo. Our per-type breakdown shows the real shape is **per-question-type**: at a single 54% compression point, `single-session-assistant` gains +36.7pp while `multi-session` only gains +13.3pp. A single-number accuracy threshold undersells the interaction between compression and question semantics. The parameter defaults she recommends (`max_items` 10–15, `model_limit` matching the real model) are unchanged by our work.

---

## 4. What we learned that the reproduction doesn't cover

These are genuine new findings, not extensions.

### 4.1 Provider compaction doesn't exist the way the original RES-333 ask assumed

Karina's reproduction is Headroom-only. We took RES-333's literal framing ("compare with openai compaction, anthropic compaction") and tried to build the comparison, which forced us to read the provider SDKs:

- **Anthropic `messages.create(context_management={clear_tool_uses, clear_thinking})`**: lossy block clearing — no-op on LongMemEval (no tool uses, no thinking turns).
- **Anthropic `beta.messages.tool_runner(compaction_control=...)`**: summarization, but **only fires inside tool-runner iterations**. Forcing it onto a non-tool benchmark requires dummy-tool scaffolding that distorts both tokens and behavior (our smoke run hung for 22 minutes on pydantic validation errors from the model mis-calling dummy tools).
- **OpenAI `responses.create(truncation="auto")`**: lossy first-N drop, only fires when input exceeds the context window. With gpt-4o-mini's 128k window and LongMemEval at ~104k, it never fires.
- **OpenAI `responses.compact()`**: direct API probe on gpt-4o-mini — **it is an analytics endpoint**. The `CompactedResponse` it returns has no assistant output and its `id` is not chainable (`400 previous_response_not_found` when used as `previous_response_id`). It reports how the conversation *would be* compacted; it is not itself a compaction primitive.

**Neither provider ships summarization-based compaction at the standard API level for non-tool-using benchmarks.** That's itself a deliverable for RES-333 — it strengthens the case that Headroom fills a real gap. Not addressable through the reproduction's interactive surface.

### 4.2 Summary-prompt is schema-shaped

Feature A (Haiku 4.5 structured summary with `decisions / constraints / rejected_paths / file_refs / facts`) was tested in parallel with Headroom. It achieves ~40% compression cleanly but is **dominated by Headroom on 5 of 6 types**. The root cause we can identify: the schema is shaped for SWE/planning workloads, not for casual conversational recall ("what degree did I graduate with", "how long is my commute"). Karina's reproduction doesn't evaluate a summary-prompt alternative, so this is a new (negative) finding.

**Counter-nuance:** Feature A is the only arm that clears 0% on temporal-reasoning (+6.7pp) and posts modest positive deltas on 5 of 6 types (grand mean +6.3pp). A schema redesign for conversational tasks might flip the verdict — not a dead end, just schema-shaped.

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
