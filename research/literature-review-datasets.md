# Literature review — benchmark datasets for Headroom

**Date:** 2026-04-08
**Author:** Research scan (web + Hugging Face Hub + arxiv)
**Audience:** Kiran + Headroom eng — input to the ship/flag/drop decision for this quarter.

## Context

Headroom compresses agent context (tool-call outputs, logs, DB reads, RAG
results, file reads, API responses) before it hits the LLM. Our current
benches are thin:

- One HTML-extraction test
- Flat JSON compression metrics
- Some synthetic adversarial stress tests

What's missing is the real workload our users push through context: **long
multi-turn agent conversations that interleave code, natural-language
reasoning, and JSON/tool-call outputs**. Coding agents (Claude Code, Cursor,
Aider), RAG pipelines, and data-analysis agents all look like this, and none of
our existing benches actually exercise it.

This document surveys candidate datasets we could adopt — from academic
literature and the Hugging Face Hub — and picks the ones worth integrating
first.

## Goal this feeds into

Produce one report that, for each of the five compression arms, reports:

1. Compression ratio
2. End-to-end latency
3. Quality on **LoCoMo QA** (by category) — the decided quality yardstick
4. Cost

The report must be conclusive enough for Kiran to decide whether Headroom ships
this quarter, ships behind a flag, or is dropped.

LoCoMo is already locked in as the quality signal. The datasets picked below
are the **inputs** that feed the compression/latency/cost measurements, and
they are chosen to complement LoCoMo's weaknesses (LoCoMo is heavy on
natural-language dialogue memory; it is *not* heavy on code or JSON tool
calls).

---

## 1. Long-context general benchmarks

| Dataset | What it is | Relevant? |
|---|---|---|
| **LongBench v2** (`THUDM/LongBench-v2`) | 503 multiple-choice QA, 8k–2M words, 6 categories — includes *long-dialogue history*, *code repo understanding*, and *long structured data*. Even o1-preview only hits 57.7%. | **Yes** — the long-dialogue + structured-data + code-repo tasks are exactly Headroom's target modalities. MCQ format makes eval reliable. |
| **LongBench v1** (`THUDM/LongBench` / `zai-org/LongBench`) | Bilingual, 21 tasks, ≤~32k context. The canonical baseline — LLMLingua, LLMLingua-2, LongLLMLingua all report on it. | **Yes** — reuse the exact splits compression papers report on so we can plot head-to-head. |
| **RULER** (`NVIDIA/RULER`) | 13 synthetic tasks across retrieval/multi-hop/aggregation/QA, configurable sequence length. | Partial — synthetic, not agent-realistic. Good as a *controlled* upper-bound stress test for retention under compression. |
| **HELMET** (`princeton-nlp/HELMET`) | 7 application-centric categories, designed to fix ZeroSCROLLS/LongBench/InfiniteBench limitations. | **Yes** — the most defensible general long-context bench in 2025/26; reviewers will expect it. |
| **InfiniteBench** (`OpenBMB/InfiniteBench`) | 12 tasks at 100k+ tokens. | Partial — mostly document reasoning, not agent traces. |
| **ZeroSCROLLS** | Zero-shot long-doc tasks. | Skip — superseded by HELMET, but LLMLingua-2 reports on it for historical comparison. |

## 2. Agent trajectory / tool-use datasets — highest priority for the gap

| Dataset | Contents | Size | License | Notes |
|---|---|---|---|---|
| **`nvidia/Nemotron-Agentic-v1`** | Synthetic multi-turn trajectories: user goal → agent reasoning → tool calls → JSON tool responses → reasoning. Judge-filtered for quality. | Large | **CC-BY-4.0, commercial OK** | **Best license/shape match.** Exactly "NL + reasoning + JSON tool outputs interleaved." Drop-in for Headroom. No docker harness required. |
| **`nebius/SWE-rebench-openhands-trajectories`** | Real OpenHands trajectories on 1,823 Python repos. Full code + stdout + tool calls + agent reasoning + JSON observations. | 67,074 trajectories (32k successful) | Open (see repo) | **Closest to real coding-agent workload.** Heavy mix of code, bash output, file reads, JSON. Very long contexts. |
| **`nebius/SWE-agent-trajectories`** | 80,036 SWE-agent trajectories on SWE-bench-extra + dev split. | 80k | Open | Same shape, different scaffold. Good for cross-scaffold generalization. |
| **`SWE-bench/SWE-smith-trajectories`** | 5,017 curated trajectories used to train SWE-agent-LM-32B (40.2% on Verified). | 5k | Open | Smaller, high-quality curated set. |
| **`ByteDance-Seed/Multi-SWE-bench_trajs`** | Multi-language SWE trajectories (Java/Go/Rust/TS/…). | — | Open | Use if we want to show Headroom isn't Python-specific. |
| **`Salesforce/xlam-function-calling-60k`** | 60k function-calling conversations across 3,673 APIs, 21 categories. | 60k | CC-BY-4.0 | Shorter, denser — good for measuring compression of JSON tool schemas + arguments specifically. |
| **`xlangai/AgentNet`** | 22.6k human-annotated desktop computer-use trajectories. | 22.6k | Open | Mostly screenshots+actions — out of scope unless we care about CUA. |
| **BFCL v3/v4** (`gorilla-llm/Berkeley-Function-Calling-Leaderboard`) | Multi-turn & multi-step function calling; 200 Base Multi-Turn examples plus more categories. | ~11 MB JSON | Apache-2.0 | **Small but canonical.** Every function-calling paper reports on BFCL — we almost have to include it. |
| **τ-bench / τ²-bench** (`sierra-research/tau-bench`, `sierra-research/tau2-bench`) | Retail/airline/telecom tool+user simulated dialogues; `pass^k` reliability metric. | Hundreds of tasks | MIT | **High signal** — emulates a realistic user-agent-tool loop with policy constraints. Use for end-to-end accuracy-under-compression. |
| **AppWorld** (`StonyBrookNLP/appworld`) | 9 apps, 457 APIs, 750 tasks, ~100 fictitious users. GPT-4o only hits ~49%. ACL'24 Best Resource Paper. | 750 tasks | Apache-2.0 | Runs in a docker-ish engine; trajectories are interactive code + API responses. Heavy to integrate but high quality. |
| **GAIA** (`gaia-benchmark/GAIA`) + **GAIA2/ARE** | 466 real-world assistant questions, 3 difficulty levels, web + tool + multimodal. | 466 | Apache-2.0 | Flagship general-agent bench. GAIA2 adds a smartphone simulator. Good headline number but small sample. |

## 3. Code-heavy long-context

| Dataset | Contents | Why it helps |
|---|---|---|
| **Long Code Arena** (`JetBrains-Research/lca-*`) | 6 tasks: library-based codegen, CI build repair, project-level completion, commit-msg generation, bug localization, module summarization. Bucketed by context size (0–48k / 48–192k / 192–768k / 768k+ chars). | **Top pick for code long-context.** Real repos, project-wide context, clean eval suite. |
| **RepoBench / CrossCodeEval** | Multi-file code completion at repo scale. | Narrower than LCA, but more cited in older papers. |
| **LongCodeBench** (arxiv 2505.07897) | Coding LLMs at 1M-token contexts. | New; useful if we ever claim 1M support. |

## 4. Real multi-turn conversation corpora

| Dataset | Notes | License |
|---|---|---|
| **`allenai/WildChat-1M`** | 1M real user↔ChatGPT conversations, many long. | **ODC-BY** — commercial OK, attribution required. Redistributable. |
| **`lmsys/lmsys-chat-1m`** | 1M Vicuna-arena conversations. | Custom LMSYS license — research + commercial permitted, but creators can request deletion. Do **not** redistribute a fork. |
| **MultiChallenge** (Scale, ACL'25 — `ekwinox117/multi-challenge`) | 4 capability categories: instruction retention, inference memory, versioned editing, self-coherence. Frontier models <50%; Claude 3.5 Sonnet 41.4%. | Open on GitHub | Small but *the* multi-turn bench that exposes context-handling regressions — perfect for catching compression-induced forgetting. |
| **MT-Bench** (LMSYS) | 80 two-turn questions, judge-scored. | Apache-2.0 | Legacy but cheap sanity check. |

## 5. Prompt-compression-specific benchmarks

These are what LLMLingua-2 / LongLLMLingua / RECOMP actually report on — reuse
them so the numbers are directly comparable to published baselines.

- **MeetingBank** + **`microsoft/MeetingBank-QA-Summary`** /
  **`microsoft/MeetingBank-LLMCompressed`** — LLMLingua-2's in-domain
  training/eval. 862 transcripts, QA+summary pairs.
  License: **CC-BY-NC-SA 4.0** → **research use only, not redistributable in a
  commercial product.** Flag this before bundling.
- **LongBench (v1)** — out-of-domain eval in LLMLingua-2 paper.
- **ZeroSCROLLS** — out-of-domain eval in LLMLingua-2.
- **GSM8K / BBH** — LLMLingua-2 reports compression-under-reasoning numbers on
  these. Tiny, Apache/MIT — safe to bundle.
- **`microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`** — the
  reference compressor model; run Headroom head-to-head on the same inputs.

---

## Top 5 picks (long list)

Ranked for the "long multi-turn mixing code + text + JSON" gap, with license
and integration cost weighed in:

1. **`nvidia/Nemotron-Agentic-v1`** — CC-BY-4.0, exactly the modality mix, commercially usable, no docker harness. Start here.
2. **`nebius/SWE-rebench-openhands-trajectories`** — real coding-agent sessions, huge, open, authoritative for our headline audience.
3. **Long Code Arena** (`JetBrains-Research/lca-project-level-code-completion` + CI-repair split) — clean repo-scale code long-context with pre-bucketed context sizes; perfect for compression-ratio-vs-task-accuracy curves.
4. **LongBench v2** (`THUDM/LongBench-v2`) — defensible academic baseline, MCQ eval is cheap and reliable, covers dialogue/code-repo/structured-data in one package. Reviewers will expect it.
5. **τ²-bench** (sierra-research) — closes the loop with a real user↔agent↔tool simulated environment; `pass^k` reliability metric lets us measure whether compression *silently degrades* consistency, which flat QA benches miss.

**Honorable mention:** BFCL v3 — tiny, so add it as a cheap sanity bench
alongside LongBench v1. Drop MeetingBank for any commercial claim (NC license),
but keep it for research-mode apples-to-apples against LLMLingua-2.

---

## The two picks for this quarter

For the 5-arm report Kiran needs to make a ship/flag/drop call, the decision
criterion is: **which datasets fill the code + JSON + multi-turn gap that
LoCoMo leaves open, with the smallest integration cost?**

LoCoMo is strong on long natural-language dialogue with memory but weak on
code and JSON tool-call density. The two picks should cover that gap with
minimum harness overhead — we are measuring compression ratio, latency, and
cost, all of which require running every arm on every sample, so heavy harness
setups (AppWorld, τ²-bench) are a risk to the timeline.

### Pick 1 — `nvidia/Nemotron-Agentic-v1`

**Why:** Purest match for the gap. Every sample is a multi-turn trajectory
with user NL → agent reasoning → JSON tool call → JSON tool response → more
reasoning. That is *exactly* the modality mix Headroom is supposed to compress
and which is missing from our current benches. Judge-filtered quality means
we don't need to do our own curation pass.

**Integration cost:** Minimal. Loads from HF with `datasets.load_dataset`, no
docker, no external APIs, no env setup. A benchmark runner can stream it.

**License:** CC-BY-4.0 — commercial use is fine, attribution required. We can
publish numbers and redistribute derived results without legal review.

**What it gives the 5-arm report:**
- Compression ratio on realistic JSON-heavy tool outputs (the "flat JSON" problem, but with surrounding dialogue context).
- Latency numbers that reflect actual agent turn structure.
- Cost numbers on the token mix our users actually see.
- Complements LoCoMo by adding structured tool-call density on top of multi-turn reasoning.

### Pick 2 — `nebius/SWE-rebench-openhands-trajectories`

**Why:** Real coding-agent sessions on 1,823 Python repos. Files get read,
bash gets run, stdout comes back, diffs get applied, JSON observations flow
through. This is the *single most representative* dataset for Headroom's
flagship "coding agent" use case, and it is the one workload where the 70–95%
boilerplate compression claim can be stress-tested on real data instead of
synthetic inputs.

**Integration cost:** Moderate. Large dataset (67k trajectories), will need
streaming + a sampling strategy (e.g. 200–500 trajectories stratified by
success/length). No docker harness needed to *read* the trajectories, only to
regenerate them — and we don't need to regenerate.

**License:** Open, released by Nebius alongside RFT checkpoints.

**What it gives the 5-arm report:**
- The realistic long-context distribution that coding-agent users will actually hit (tens to hundreds of thousands of tokens per session).
- A quality signal orthogonal to LoCoMo: does compression destroy the code/stdout/JSON information the agent needs for its *next* step?
- Cost + latency at the length where compression actually pays for itself.

### Why not the other three

- **Long Code Arena** — great dataset, but it is code-completion-shaped, not agent-trajectory-shaped. It would overlap too much with SWE-rebench for the amount of integration work. Keep on the backlog for a v2 report.
- **LongBench v2** — academically defensible but MCQ format does not stress the tool-call JSON axis. Add later if reviewers push back.
- **τ²-bench** — highest signal for end-to-end reliability, but it needs the sierra-research harness and dual-control user simulation. This is a timeline risk for a ship-this-quarter decision. Defer to v2.

### Combined picture

**LoCoMo** (natural dialogue memory, quality gold) + **Nemotron-Agentic-v1**
(conversational tool use, compression-ratio + cost) + **SWE-rebench-openhands-trajectories**
(real coding-agent traces, long-context stress) gives Kiran three distinct
workloads that together span the actual Headroom target: dialogue memory,
structured tool use, and long coding-agent sessions. Two of the three are
drop-in HF loads; LoCoMo was already on the roadmap. That is achievable this
quarter.

---

## Sources

- [zai-org/LongBench-v2 (HF)](https://huggingface.co/datasets/zai-org/LongBench-v2)
- [LongBench v2 paper — arxiv 2412.15204](https://arxiv.org/abs/2412.15204)
- [LongBench v1 (HF)](https://huggingface.co/datasets/zai-org/LongBench)
- [NVIDIA RULER (GitHub)](https://github.com/NVIDIA/RULER)
- [RULER paper — arxiv 2404.06654](https://arxiv.org/abs/2404.06654)
- [HELMET benchmark (Princeton NLP)](https://github.com/princeton-nlp/HELMET)
- [HELMET blog (HF)](https://huggingface.co/blog/helmet)
- [InfiniteBench (GitHub)](https://github.com/OpenBMB/InfiniteBench)
- [LLMLingua-2 paper — arxiv 2403.12968](https://arxiv.org/abs/2403.12968)
- [LLMLingua-2 project page](https://llmlingua.com/llmlingua2.html)
- [microsoft/MeetingBank-QA-Summary (HF)](https://huggingface.co/datasets/microsoft/MeetingBank-QA-Summary)
- [microsoft/MeetingBank-LLMCompressed (HF)](https://huggingface.co/datasets/microsoft/MeetingBank-LLMCompressed)
- [nvidia/Nemotron-Agentic-v1 (HF)](https://huggingface.co/datasets/nvidia/Nemotron-Agentic-v1)
- [nebius/SWE-rebench-openhands-trajectories (HF)](https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories)
- [Nebius OpenHands trajectories blog](https://nebius.com/blog/posts/openhands-trajectories-with-qwen3-coder-480b)
- [nebius/SWE-agent-trajectories (HF)](https://huggingface.co/datasets/nebius/SWE-agent-trajectories)
- [SWE-bench/SWE-smith-trajectories (HF)](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories)
- [ByteDance-Seed/Multi-SWE-bench_trajs (HF)](https://huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench_trajs)
- [Salesforce/xlam-function-calling-60k (HF)](https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k)
- [xlangai/AgentNet (HF)](https://huggingface.co/datasets/xlangai/AgentNet)
- [BFCL dataset (HF)](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)
- [BFCL v3 multi-turn blog](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)
- [τ-bench (GitHub)](https://github.com/sierra-research/tau-bench)
- [τ²-bench (GitHub)](https://github.com/sierra-research/tau2-bench)
- [τ-bench paper — arxiv 2406.12045](https://arxiv.org/abs/2406.12045)
- [τ²-bench paper — arxiv 2506.07982](https://arxiv.org/abs/2506.07982)
- [AppWorld (GitHub)](https://github.com/StonyBrookNLP/appworld)
- [AppWorld paper — arxiv 2407.18901](https://arxiv.org/abs/2407.18901)
- [GAIA dataset (HF)](https://huggingface.co/datasets/gaia-benchmark/GAIA)
- [GAIA2 / ARE blog](https://huggingface.co/blog/gaia2)
- [Long Code Arena paper — arxiv 2406.11612](https://arxiv.org/abs/2406.11612)
- [JetBrains-Research/lca-project-level-code-completion (HF)](https://huggingface.co/datasets/JetBrains-Research/lca-project-level-code-completion)
- [LongCodeBench — arxiv 2505.07897](https://arxiv.org/html/2505.07897v2)
- [allenai/WildChat-1M (HF)](https://huggingface.co/datasets/allenai/WildChat-1M)
- [lmsys/lmsys-chat-1m (HF)](https://huggingface.co/datasets/lmsys/lmsys-chat-1m)
- [MultiChallenge paper — arxiv 2501.17399](https://arxiv.org/abs/2501.17399)
- [MultiChallenge (ACL 2025)](https://aclanthology.org/2025.findings-acl.958/)

---

## Integration status (2026-04-08)

Both picks are now loadable via `headroom.evals.datasets`:

```python
from headroom.evals.datasets import load_dataset_by_name

# Nemotron-Agentic-v1 (tool-use modality gap)
nemotron = load_dataset_by_name("nemotron_agentic_v1", n=200)

# LongBench v1 multi-task suite (LLMLingua-2 head-to-head)
longbench = load_dataset_by_name("longbench_v1_suite", n_per_task=50)
```

Registered names:
- `nemotron_agentic_v1` (category: `tool_use`) — wraps `nvidia/Nemotron-Agentic-v1`,
  splits each trajectory at the last user turn into `(context, query, ground_truth)`.
- `longbench_v1_suite` (category: `long_context`) — concatenates the 16
  LongBench v1 tasks from the LLMLingua-2 paper into a single EvalSuite with
  per-case `metadata["task"]` so breakdowns remain possible.

Tests: `tests/test_evals/test_dataset_loaders.py`
- Unit tests use hand-built fixtures + monkeypatched `datasets.load_dataset`.
- Integration smoke tests are guarded by `@pytest.mark.integration` and skipped
  by default. Run locally with `pytest -m integration`.
