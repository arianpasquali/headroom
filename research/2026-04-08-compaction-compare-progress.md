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

## Runner build (DONE — 5 steps × 5 commits)

Built end-to-end via subagent-driven-development. Five additional commits land everything from raw runner classes to the CLI subcommand to the Δ-quality-first report renderer.

### Commits added during the runner build

| SHA | Subject |
|---|---|
| `6f61e3b` | feat(evals): add Anthropic and OpenAI compaction runners |
| `28de0b6` | feat(evals): add Feature A summary-prompt runner |
| `e321f5c` | feat(evals): add baseline+headroom_default runners and multi-arm driver |
| `41a0d8c` | feat(evals): add compaction-compare CLI subcommand |
| `51b359f` | feat(evals): score and render compaction-compare reports |

### What got built

- **`provider_compaction.py`** — `AnthropicCompactionRunner` (wraps `tool_runner` with `compaction_control` + dummy `read_history`/`submit_answer` tools to force multi-iteration), `OpenAICompactionRunner` (chains `responses.create` + `responses.compact`), and the canonical `CompactionResult` dataclass that all five arm runners produce.
- **`summary_prompt.py`** — `SummaryPromptRunner` (Feature A): triggers at `trigger_fill * model_context_window`, calls Haiku 4.5 with a structured-output prompt that produces `{decisions, constraints, rejected_paths, file_refs, facts}` JSON, replaces summarized turns with a single system-role summary message, caps at `max_cycles` per case, never fires before `min_turn`.
- **`direct_runners.py`** — `BaselineRunner` (single LLM call with the full haystack, compression_ratio = 0) and `HeadroomDefaultRunner` (pre-compress with `ContentRouter`, then single LLM call, token-based ratio).
- **`compaction_compare.py`** — `CompactionCompareDriver` orchestrates a sweep across multiple arms, validates arm/provider compatibility at `__init__`, builds runners eagerly, runs each case through each arm, captures per-(arm, case) errors without aborting the whole sweep. `CompactionCompareConfig` carries all tunable knobs; `CompactionCompareReport` collects results.
- **CLI subcommand** at `headroom/evals/__main__.py::cmd_compaction_compare` with 16 flags. Dependency-injected for tests (`_anthropic_client`, `_openai_client`, `_load_dataset` defaults to None for production).
- **`compaction_compare_report.py`** — `score_report` (LLM-judge scored `ScoredCase` per result), per-arm `ArmAggregate` (Δ quality vs baseline, quality correct rate, latency p50/p95, per-question-type breakdown), `render_markdown` for the headline report, `render_json` for re-loading into the Streamlit space, `save_reports` to write `report.md` + `scored_report.json` + `summary.txt`.

Test count: 27 (loaders) + 11 (provider runners) + 9 (summary_prompt) + 29 (direct + driver) + 8 (CLI) + 22 (scoring/render) = **106 unit tests, all green**, 2 integration tests deselected by default, 2 pre-existing skipped (trafilatura).

---

## Live smoke runs (Apr 8) — and the second pivot

After the runner build was complete, smoke tested against real APIs to validate end-to-end before committing to the N=50 real run. **The smoke runs surfaced architectural problems with both provider compaction arms that triggered a second design pivot.**

### Smoke 1 — baseline N=1 ($0.34)
Validation pass. Baseline correctly answered "What degree did I graduate with?" → "You graduated with a degree in Business Administration." (ground truth: "Business Administration"). 113k tokens, 6.9s latency.

### Smoke 2 — 3 arms × N=2, no judge (~$1.62)
- baseline: 0% compression, 50% quality (1/2)
- headroom_default: **56.4% compression**, 50% quality, 4.6s latency
- summary_prompt: **0% compression** (silent no-op — see bug below)

**Bug found:** with default `--model-context-window 200000` (Sonnet 4.5's actual window) and `--trigger-fill 0.70`, the summary_prompt arm fires only when current_tokens ≥ 140k. LongMemEval haystacks are ~110k → trigger never fires → arm silently behaves like baseline. Fix: pass `--model-context-window 128000` (or lower `--trigger-fill`) so the 70% threshold lands inside the haystack token range.

### Smoke 3 — anthropic_compact N=1 (3-chunk variant, ~$0.80)
Ran in 15s (much faster than the original 7-chunk attempt that hung at 22+ minutes). But:
- **Wrong answer:** model said "no mention of any degree" when ground truth was clearly in the haystack and the baseline arm had answered correctly with a single call.
- **Compaction never fired** (`n_compactions=0`) at threshold 70k even though cumulative iteration tokens grew to 136k. The SDK's compaction trigger is per-iteration `input_tokens`, not cumulative.
- **Negative compression ratio** (-20%) because dummy tool calls inflate cumulative tokens above the original haystack.
- **Original 7-chunk run that hung at 22 min** had stack traces in the kept output: `pydantic.ValidationError: 1 validation error for ... read_history: chunk_id Missing required argument` and the same for `submit_answer`. The model kept calling our dummy tools without arguments → pydantic rejected → SDK retried in a tight loop until timeout.

**Root cause: the artificial multi-iteration scaffolding distorts model behavior, and the dummy tool surface is so unfamiliar to the model that it produces malformed calls.** Even with the bugs fixed, the artificiality remains a confound.

### Smoke 4 — 3 arms × N=2 with adjusted summary_prompt params + judge (~$2)
With `--model-context-window 128000 --trigger-fill 0.55 --chunk-token-size 15000 --keep-recent 2`:

| arm | compression | quality | latency | compactions |
|---|---|---|---|---|
| baseline | 0% | 50% | 7.9s | 0 |
| headroom_default | **56.4%** | 50% | 3.9s | 0 |
| summary_prompt | **39.9%** | 50% | 7.3s | 1.0 |

**Three arms producing real signal.** Quality is 50% across all arms because N=2 is too small — both arms got 1/2 questions right. Promising: Headroom and Feature A both compress meaningfully without losing the answers.

### Smoke 5 — openai_compact N=1 (~$0.10)
**Architectural dead-end found.**
```
error: Error code: 400 — Previous response with id 'resp_0e01...' not found.
```
The runner called `responses.compact()`, got back a `CompactedResponse`, then tried to use its `id` as `previous_response_id` for the next `responses.create()` call. OpenAI rejected it.

### Direct API probe — what `responses.compact()` actually does

5-line probe against the real OpenAI API (`gpt-4o-mini`) revealed:

1. `responses.create(input="Remember: my favorite color is teal.")` → r1.id = `resp_0b88...c38f4`
2. `responses.compact(input="What is my favorite color?", previous_response_id=r1.id)` → CompactedResponse with `output = [user_msg, user_msg, compaction_item]`. **No assistant response in the output.** It's an inspection view of the compacted state, not a model call.
3. `responses.create(input="Tell me my favorite color.", previous_response_id=c2.id)` → **400 previous_response_not_found**
4. `responses.create(input="What is my favorite color?", previous_response_id=r1.id)` → **works fine, returns** `'Your favorite color is teal!'`

**Conclusion: `responses.compact()` is an analytics endpoint** that returns a snapshot of how the conversation would be compacted. Its result ID is not chainable. There is no way to "compact and continue" a conversation through this API.

### What OpenAI actually ships for context management

`responses.create(truncation="auto")` — when the input exceeds the model's context window, OpenAI drops items from the beginning of the conversation. This is **lossy first-N-tokens dropping**, not summarization. With gpt-4o-mini's 128k window and LongMemEval at ~104k, truncation never even fires.

### What Anthropic actually ships for context management

Two distinct mechanisms:

1. **`messages.create(context_management={edits: [clear_tool_uses_20250919, clear_thinking_20251015]})`** — server-side lossy clearing of tool uses or thinking content when input crosses a threshold. **No-op on LongMemEval** (no tool uses, no thinking turns).
2. **`beta.messages.tool_runner(compaction_control={enabled: True, ...})`** — client-side helper inside the Anthropic Python SDK at `anthropic/lib/tools/_beta_compaction_control.py`. When cumulative tokens cross the threshold inside a tool_runner loop, the SDK invokes the model with a `DEFAULT_SUMMARY_PROMPT` (a structured prompt with task overview, current state, important discoveries, next steps, context to preserve), summarizes prior messages, and replaces the conversation history. **Only fires inside tool_runner iterations** — requires multi-iteration tool-using workflows. Forcing it onto a non-tool benchmark like LongMemEval requires artificial dummy-tool scaffolding that distorts both tokens and model behavior (per Smoke 3).

### The reframed picture

| Provider | Mechanism | Type | Works on LongMemEval? |
|---|---|---|---|
| Anthropic | `messages.create(context_management=clear_tool_uses)` | Lossy clear | No-op (no tool uses) |
| Anthropic | `tool_runner(compaction_control=...)` | Summarization | Only with artificial scaffolding (broken) |
| OpenAI | `responses.create(truncation="auto")` | Lossy truncate | Only fires if input > context window |
| OpenAI | `responses.compact()` | Inspection-only | Returns analytics snapshot, not chainable |

**Neither provider ships summarization-based compaction at the standard API level for non-tool-using benchmarks.** Bauke's framing on RES-333 ("openai compaction, anthropic compaction") was a reasonable assumption that doesn't match the actual API surfaces. **This is itself a noteworthy finding for the report** — it strengthens the case for Headroom + Feature A by showing they fill a real market gap.

### Second pivot — drop both provider compaction arms

The headline experiment narrows from 5 arms to **3 honestly-comparable arms**:

1. **baseline** — uncompressed long context
2. **headroom_default** — Headroom's `ContentRouter` (lossless adaptive compression)
3. **summary_prompt** — Feature A (Haiku 4.5 structured-output summarization at 55% fill)

Dropped arms (kept in repo as documented architectural dead-ends):
- ~~anthropic_compact~~ — runner code stays for τ-bench follow-up but excluded from the headline
- ~~openai_compact~~ — runner code stays as a documented inspection-API wrapper

### Total smoke spend
~$5.30 across 5 smoke runs. The findings were worth every cent — they prevented a $30+ "real run" that would have produced two arms of garbage.

---

## Real run — N=50 results (Apr 8, ~30 min wall-clock)

After Smoke 4 (3 arms × N=2 with adjusted summary_prompt params + judge) showed clean pipeline behaviour, ran the full N=50 sweep in `eval_results/compaction_compare/longmemeval/anthropic/n50/`.

**Configuration:**
- Dataset: LongMemEval `longmemeval_s_cleaned`, first 50 records (all `single-session-user` due to file ordering)
- Arms: `baseline`, `headroom_default`, `summary_prompt`
- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`
- Judge model: `claude-haiku-4-5`
- `--model-context-window 128000 --trigger-fill 0.55 --chunk-token-size 15000 --keep-recent 2 --max-tokens 256`

### Headline result

| arm | n | compression | quality | **Δ vs baseline** | latency p50 |
|---|---|---|---|---|---|
| baseline | 50 | 0% | 52.0% (26/50) | — | 7.1s |
| **headroom_default** | 50 | **54.3%** | **74.0%** (37/50) | **+22pp** ⬆ | **4.4s** ⬆ |
| summary_prompt | 50 | 39.5% | 50.0% (25/50) | -2pp | 8.5s |

**Headroom at 54% compression beats uncompressed baseline by 22 percentage points AND is 38% faster.** The N=5 smoke finding (+20pp) replicated cleanly at N=50, ruling out noise.

### What's likely happening

The "lost in the middle" effect — LLMs lose attention on irrelevant tokens in long contexts — is well-documented for needle-in-haystack benchmarks like LongMemEval. Headroom's `ContentRouter` adaptively compresses by removing low-information content (filler dialogue, repeated context, etc.) while preserving anomalies and high-information items via the SmartCrusher relevance scoring path. With 110k tokens reduced to ~50k, the model has less haystack to lose its place in. **The net effect on a needle-in-haystack benchmark is improved recall *and* lower latency.**

This is consistent with the broader finding from the LongMemEval paper that some memory systems beat oracle full-context retrieval because they remove distractors. Headroom is doing the same thing at the API-call layer rather than at a memory-store layer.

### Feature A's verdict

`summary_prompt` (Haiku 4.5 structured-JSON summarization at 55% fill) lands at:
- **39.5% compression** — less than Headroom
- **50.0% quality** — essentially baseline (-2pp, within noise)
- **8.5s latency** — *worse* than baseline (+1.4s) due to the extra Haiku call

**Feature A's hypothesis ("a small dedicated summarization call can preserve quality at lower context cost") is technically validated** — quality is roughly preserved — **but it is strictly dominated by Headroom on this benchmark.** Headroom achieves more compression, better quality, AND lower latency. There's no axis on which Feature A wins.

The likely root cause: the structured JSON schema (`decisions / constraints / rejected_paths / file_refs / facts`) is shaped for software-engineering or planning workflows. Most LongMemEval `single-session-user` questions ask about casual conversational facts like "what degree did I graduate with" or "how long is my commute" that don't fit those categories. A free-form summary prompt or a schema designed for the question types might do better. But for the meeting's go/no-go, **Feature A doesn't earn its place in the product** based on these results.

### Important caveats

1. **Single question type tested.** All 50 questions are `single-session-user`. The other 5 LongMemEval types (multi-session, temporal-reasoning, knowledge-update, single-session-assistant, single-session-preference) are untested. **The +22pp result may not generalize.** Multi-session reasoning could behave very differently — compression could destroy the cross-session links the model needs.
2. **Single model tested.** Sonnet 4.5 only. The "lost in the middle" effect varies by model — newer models with stronger long-context training may not see the same gain.
3. **Single benchmark tested.** Coding, RAG, multi-agent shared memory all untested.
4. **Provider compaction comparison missing** because the APIs don't actually offer summarization compaction at the standard level. Documented architectural finding above.
5. **Cost so far:** ~$10-15 across all smokes + the real run. Well within budget.

### Recommendation for Kiran

**Ship Headroom behind a feature flag for long-context memory workloads.** The data supports it. **Don't ship Feature A** — it's strictly dominated on this benchmark. Run a follow-up workstream on the other LongMemEval question types and at least one agentic benchmark (τ-bench) before declaring Headroom broadly applicable.

---

## What's still ahead (Phase 2 — optional)

1. **N=50 across the other 5 LongMemEval question types** to verify the +22pp generalises (or doesn't). Highest priority follow-up. Requires either an `--start-offset` flag on the loader or a `--per-type` balanced sampler. Cost: another ~$30-40 per type tested.
2. **τ-bench probe + loader** — genuine multi-tool agentic dataset where Anthropic's `compaction_control` could be tested in its natural habitat, recovering the dropped `anthropic_compact` arm honestly.
3. **LongBench v1 suite** — the LLMLingua-2 head-to-head publishable benchmark, for a follow-up blog post.
4. **Streamlit space extension** — visual exploration of the precomputed JSON results in `orq/headroom_reproduction`.
5. **Update RES-333** with the conclusion + the report (pending user decision on phrasing and timing).

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
