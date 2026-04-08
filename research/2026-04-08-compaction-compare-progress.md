# Compaction-Compare Progress Log

> **What this is:** running log of the Headroom compaction-compare experiment build, started 2026-04-08, ahead of the RES-333 go/no-go decision. Companion to the master plan at `~/.claude/plans/shiny-conjuring-bumblebee.md` and to `research/2026-04-08-hf-benchmark-datasets.md` (the prerequisite TDD plan that's now executed).
>
> **Branch:** `feat/compaction-compare` (in worktree at `.worktrees/feat-compaction-compare/`)
>
> **Linear ticket:** [RES-333](https://linear.app/orqai/issue/RES-333/reproduce-headroom-results)

---

## Background — what triggered this work

The Apr 7 sync with Bauke handed Headroom evaluation ownership to Arian with a one-week deadline. Bauke's literal ask on RES-333:

> Baseline: uncompressed long document (perhaps longmemeval + long context agentic dataset). Compare with: openai compaction, anthropic compaction, headroom compaction, custom summary prompt.

Karina had already produced the Headroom-on-LoCoMo accuracy curve (88% baseline → 71% at 67% compression → 58% at 84% → 43% at 92%) plus parameter sensitivity analysis. The remaining gap was the **cross-arm comparison**: how does Headroom stack up against provider-native compaction (Anthropic `compaction_control`, OpenAI `responses.compact`) and a custom summary prompt at matched compression ratios?

Both providers expose compaction natively (verified via Context7) — it's no longer an open question whether the comparison is feasible.

## Step 0 — HF dataset loaders (DONE)

The original plan named two new dataset surfaces and queued up a 6-task TDD plan to add the loaders before any runner work could start.

### Commits on branch (in order)

| SHA | Subject |
|---|---|
| `bfa70bd` | chore: ignore .worktrees directory for local isolated workspaces |
| `70a30f6` | docs(research): add HF benchmark datasets implementation plan |
| `63b85cf` | test(evals): add fixtures for HF dataset loader tests |
| `6b0fc48` | feat(evals): add Nemotron-Agentic-v1 dataset loader |
| `b000be9` | feat(evals): add LongBench v1 multi-task suite loader |
| `2816f00` | test(evals): add network-gated integration smoke tests for HF loaders |
| `522a40a` | test(evals): verify new HF loaders are wired through load_dataset_by_name |
| `864b194` | docs(research): import literature review datasets doc from main working copy |
| `12e5d97` | docs(research): document HF dataset loader integration status |
| `cee81e1` | feat(evals): add LongMemEval loader (long-context memory benchmark) |

### What got built

**`load_nemotron_agentic_v1(n, split)`** at `headroom/evals/datasets.py`
- Wraps `nvidia/Nemotron-Agentic-v1` (HF dataset, deprecated as a data source for this experiment but kept as a reusable code pattern)
- Splits each trajectory at the last user turn: tools + prior messages → context, user turn → query, next assistant message → ground_truth
- One non-trivial deviation from the spec (documented in commit `6b0fc48`): for tool-call trajectories, intermediate `assistant(tool_calls)` and `tool` messages fold into the context (not into ground_truth) so the agentic loop is preserved as the LLM would see it on the next turn

**`load_longbench_v1_suite(n_per_task, tasks)`** at `headroom/evals/datasets.py`
- Wraps the existing `load_longbench` single-task loader to concatenate all 16 LongBench v1 tasks the LLMLingua-2 paper reports on
- New module-level constant `LONGBENCH_V1_TASKS` keeps the task list in sync with the paper's Table 3
- Each case carries `metadata["task"]` so per-task breakdowns remain possible

**`load_longmemeval(n, split)`** at `headroom/evals/datasets.py`
- Wraps `xiaowu0162/longmemeval-cleaned` (the cleaned successor to `xiaowu0162/LongMemEval`, which the original author deprecated)
- Streams the 277 MB JSON file via `ijson.items()` over `HfFileSystem.open(...)` — never loads the whole file into memory
- Three splits exposed: `longmemeval_s_cleaned` (default, 500 Q), `longmemeval_m_cleaned` (~2.7 GB), `longmemeval_oracle` (15 MB, only evidence sessions)
- Each question becomes one `EvalCase` with the full haystack as context, the question as query, and the canonical answer as ground_truth
- Adds `ijson>=3.0` to the `[evals]` extra in `pyproject.toml`

### Test coverage

`tests/test_evals/test_dataset_loaders.py` — **27 unit tests passing, 2 integration tests deselected by default**

| Test class | Count | What it covers |
|---|---|---|
| `TestLoadNemotronAgenticV1` | 8 | Trajectory splitting (user-end, assistant-end, tool-call), metadata, n-limit, split-name |
| `TestNemotronRegistry` | 2 | Registry lookup + load_dataset_by_name wiring |
| `TestLoadLongBenchV1Suite` | 4 | 16-task constant, suite cardinality, metadata, registry |
| `TestLoadLongMemEval` | 7 | Schema mapping, query/answer extraction, haystack-in-context, metadata, n-limit, split |
| `TestLongMemEvalRegistry` | 2 | Registry + load_dataset_by_name wiring |
| `TestDatasetRegistryWiring` | 4 | `list_available_datasets`, `load_dataset_by_name` smoke, unknown-dataset error |
| `TestRealHuggingFaceLoading` | 2 | `@pytest.mark.integration` — actually downloads from HF, deselected by default |

The integration marker is registered in `pyproject.toml` via `addopts = "-v --tb=short -m 'not integration'"` and the `markers = [...]` array, so plain `pytest` skips them and `pytest -m integration` runs them.

Test fixtures use a `_FakeHFDataset` (for the `datasets` library loaders) and a monkeypatched `HfFileSystem.open` returning `BytesIO` (for the LongMemEval ijson loader). No network in unit tests.

---

## The token-length gate — and why we pivoted

After Step 0 was scaffolded but before I dispatched the runner build, a self-review of the plan flagged six issues. The most important was a hidden assumption: **provider-native compaction only fires above a token threshold**. If the dataset is short enough that the trigger never fires, the compaction arms become no-ops and the experiment produces nothing.

I added a hard gate to the plan: **p50 ≥ 20k tokens** on the trajectory being benchmarked, to guarantee the smallest compaction threshold (25k) fires on at least half of cases.

### Measurement results

Sampled 200 trajectories from `interactive_agent`, 100 from `tool_calling`, and the full 30 LoCoMo conversations (10 conversations × 3 size measures). Used `tiktoken cl100k_base` consistently across all measurements. Streamed everything via `HfFileSystem` — no full downloads.

| Dataset | Slice | min | p50 | p90 | max | Gate |
|---|---|---:|---:|---:|---:|:---:|
| Nemotron `interactive_agent` | full trajectory (tools+messages JSON) | 2,997 | **3,615** | 4,328 | 6,367 | **FAIL** |
| Nemotron `tool_calling` | full trajectory (tools+messages JSON) | 268 | **3,924** | 7,694 | 16,612 | **FAIL** |
| LoCoMo | per session | 299 | 623 | 955 | 1,378 | FAIL (way under) |
| LoCoMo | full conversation (29 sessions concat) | 11,074 | **19,428** | 21,311 | 21,371 | **FAIL by 572 tokens** |
| **LongMemEval `s_cleaned`** | haystack per question (sample of 30) | 100,115 | **103,953** | 105,714 | 105,874 | **PASS (5×)** |

### What this told us

1. **Nemotron-Agentic-v1 is short-agent-demos, not long-context.** Even the largest trajectory in the entire `tool_calling` split (16.6k tokens) is below our smallest compaction threshold. At matched thresholds, zero arms would fire. Useless as a comparison surface for this experiment. The loader stays in the repo as a reusable code pattern but the dataset is deprecated for the compaction-compare report.
2. **LoCoMo is borderline-but-fails.** Conversations cluster tightly around 19–21k tokens with N=10. At Anthropic's *default* 100k compaction trigger, zero LoCoMo conversations fire. Forcing the trigger down to 15k to make the comparison fire is a 5× drop from the natural setting and renders the comparison artificial. Plus N=10 with a narrow range gives almost no statistical power for a Pareto curve.
3. **LongMemEval `s_cleaned` is the right surface.** 500 questions × 6 question types (multi-session 133, temporal-reasoning 133, knowledge-update 78, single-session-user 70, single-session-assistant 56, single-session-preference 30), ~48 haystack sessions per question, p50 ≈ 104k tokens. Decisively above the gate. It's also literally what Bauke asked for in his Apr 7 RES-333 comment.

### Live verification

After building the LongMemEval loader, ran a real network load of 2 records from `s_cleaned`:

```
longmemeval_e47becba: 53 sessions, 529,220 chars context (≈ 132k tokens)
longmemeval_118b2229: 45 sessions, 522,643 chars context (≈ 130k tokens)
```

Live record sizes are even higher than the sample-of-30 average — confirms the dataset will exercise compaction at any sensible threshold.

---

## Plan pivot — what changed

The master plan at `~/.claude/plans/shiny-conjuring-bumblebee.md` originally proposed three dataset surfaces (LoCoMo + Nemotron + LongBench v1 suite). After the gate failure I pivoted it to:

| Dataset | Role | Why |
|---|---|---|
| **LongMemEval `s_cleaned`** | **Primary** — all five arms run here | Only candidate that decisively passes the token-length gate; matches Bauke's literal ask; 500 questions across 6 types gives real statistical power |
| LongBench v1 suite | Phase 2 optional | LLMLingua-2 head-to-head surface for a follow-up blog post; not on the critical path for Kiran's go/no-go this week |
| LoCoMo | Appendix only | Karina's existing 67%/84%/92% Headroom curve cited as supporting context, **not re-run**, not in the headline cross-arm table |
| Nemotron-Agentic-v1 | Deprecated | Loader stays in repo as reusable code; not used in this experiment |

**Known gap acknowledged but not closed this week:** no "long context AND agentic" surface. Bauke's original framing wanted both. Nemotron failed; τ-bench unprobed; LongMemEval is long but not tool-use-agentic. The final report will state this explicitly as a follow-up workstream.

### Compaction threshold sweep updated

Original plan swept `{25k, 50k, 100k}` to land arms near 67% compression on LoCoMo. With LongMemEval at p50 ≈ 104k, the new sweep is `{50k, 75k, 100k}` — Anthropic's default 100k trigger fires on most questions, 50k fires on essentially all of them.

---

## What's still ahead

This is the runner-build phase. Five steps from the master plan:

1. **Provider-compaction adapters** (`headroom/evals/runners/provider_compaction.py` — new). Two thin classes: `AnthropicCompactionRunner` wrapping `client.beta.messages.tool_runner(..., compaction_control=...)`, and `OpenAICompactionRunner` wrapping `client.responses.create()` + `client.responses.compact()`. Both return per-case results that slot into the existing `EvalResult` dataclass (`headroom/evals/core.py:68-123`).

2. **Feature A summary-prompt strategy** (`headroom/evals/runners/summary_prompt.py` — new). The Haiku 4.5 custom summary the user proposed: triggers at 70% context fill, structured JSON output (decisions / constraints / rejected_paths / file_refs), never on turns 1-3, max 3 cycles per session.

3. **Multi-arm driver** — extend `headroom/evals/memory/runner_v3.py` with an `arms` parameter so a single LongMemEval pass can iterate each question through every requested arm and tag results with the arm label. No changes to scoring or judge logic.

4. **CLI entrypoint** — add `compaction-compare` subcommand to `headroom/evals/__main__.py` that takes `--dataset longmemeval -n 50 --arms ... --threshold ... --provider ... -o ...`.

5. **Report card extension** — add Δ-quality-first per-arm comparison table to `headroom/evals/reports/report_card.py`. Headline column is `Δ quality vs baseline`; supporting columns are compression ratio, p50/p95 latency, accuracy by question type, cost, compaction-event count.

6. **(Optional, time permitting)** — extend the `space/src/streamlit_app.py` HF Space to load and visualise the precomputed JSON results.

## Files of note

- Master plan: `~/.claude/plans/shiny-conjuring-bumblebee.md`
- Step 0 TDD plan (executed): `research/2026-04-08-hf-benchmark-datasets.md`
- Literature review (datasets): `research/literature-review-datasets.md`
- Existing eval infrastructure (re-used, not rewritten):
  - `headroom/evals/core.py` — `EvalCase`, `EvalResult`, `EvalSuiteResult`
  - `headroom/evals/datasets.py` — all loaders + registry
  - `headroom/evals/memory/locomo.py` — LoCoMo loader (still used as appendix)
  - `headroom/evals/memory/runner_v3.py` — LoCoMo replay harness (will be extended for multi-arm)
  - `headroom/evals/memory/judge.py` — LLM-as-judge for open-domain QA
  - `headroom/evals/metrics.py` — F1, semantic similarity
  - `headroom/evals/cost_tracker.py` — API spend tracking
  - `headroom/evals/reports/report_card.py` — Markdown / JSON / HTML reporter
- HF Space (separate, untracked): `space/src/streamlit_app.py` (Karina's interactive reproduction; symlinked to HF LFS blobs)
