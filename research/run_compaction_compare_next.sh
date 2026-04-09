#!/usr/bin/env bash
#
# Run every next-step compaction-compare experiment for RES-333.
#
# Usage:
#   ./research/run_compaction_compare_next.sh <step>
#
# All LongMemEval steps work today. All cross-dataset steps REQUIRE a runner patch
# first — see "BLOCKER" section near the bottom. The cross-dataset *smoke* variants
# are free/cheap and exist specifically so you can verify the patch before spending
# money on the full sweeps.
#
# ─── Available steps ──────────────────────────────────────────────────────────
#
# Sanity / verification
#   smoke                        2-case LongMemEval dry run, no judge. ~$0.  Verifies CLI works.
#
# LongMemEval follow-ups (work today)
#   temporal_rerun               Fix the 429-contaminated temporal-reasoning baseline.
#   n150_mixed                   Scale mixed-sample headline run from n=50 → n=150.
#   threshold_sweep              Thresholds 25k / 50k / 100k on n=50 to find the quality knee.
#   aggregate                    Roll per-type results into one cross-type Markdown report.
#   all_longmemeval              temporal_rerun + n150_mixed + threshold_sweep + aggregate.
#
# Cross-dataset smokes (require runner patch — cheap, use to verify the patch)
#   smoke_longbench              LongBench v1 suite, 2 cases, no judge.
#   smoke_hotpotqa               HotpotQA, 2 cases, no judge.
#   smoke_narrativeqa            NarrativeQA, 2 cases, no judge.
#   smoke_natural_questions      Natural Questions, 2 cases, no judge.
#   all_cross_dataset_smokes     All four smokes in sequence. ~$0.
#
# Cross-dataset full runs (require runner patch — expensive)
#   longbench_v1_suite           n=100, publishable LLMLingua-2 comparison. ~$40–60.
#   narrativeqa                  n=100, long narrative comprehension. ~$20–30.
#   hotpotqa                     n=100, multi-hop RAG. ~$10–20.
#   natural_questions            n=100, single-hop factual retrieval. ~$10–20.
#   all_cross_dataset            All four full runs, sequentially. ~$80–130.
#
# Arm-specific verification (OpenAI Responses API)
#   openai_compact_v2_smoke      2-case LongMemEval probe of the openai_compact_v2 arm
#                                on gpt-5.4 with the server-side Responses API
#                                context_management=[{...}] feature. Verifies the
#                                extra_body wire shape against the live OpenAI API.
#                                Requires OPENAI_API_KEY. ~$0 (2 cases, no judge).
#                                ✅ VERIFIED 2026-04-09: 2/2 success, n_compactions=1,
#                                both answers correct. See § 4.1.b of
#                                research/2026-04-09-streamlit-reproduction-comparison.md
#                                for the full findings and the compression-metric caveat.
#
#   compact_v2_headhead_smoke    Run anthropic_compact_v2 AND openai_compact_v2 on
#                                the SAME 2 LongMemEval cases, back-to-back, writing
#                                to separate output dirs. Lets you diff the two
#                                vendors' compaction primitives head-to-head on
#                                identical inputs. Requires BOTH keys. ~$0.
#                                Motivated by the 2026-04-09 smoke finding that
#                                openai_compact_v2 correctly answered the "commute"
#                                case that anthropic_compact_v2 is documented to
#                                fail on. Do NOT generalise from n=2 — use this
#                                step to sanity-check, then scale to n≥20 with
#                                --judge for a real comparison.
#
# Convenience
#   everything                   all_longmemeval + all_cross_dataset_smokes + all_cross_dataset.
#                                Total cost ~$100–150. Only run this if you know what you're doing.
#
# ─── Preconditions ────────────────────────────────────────────────────────────
#
#   - ANTHROPIC_API_KEY exported (required for every step EXCEPT
#     openai_compact_v2_smoke; compact_v2_headhead_smoke requires BOTH).
#   - OPENAI_API_KEY exported (required for openai_compact_v2_smoke AND
#     compact_v2_headhead_smoke).
#   - uv installed and on PATH.
#   - This script lives inside the feat/compaction-compare worktree; it cd's to
#     the worktree root on launch, so you can run it from anywhere.

set -euo pipefail

# --- Locate the worktree root regardless of caller cwd -------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${WORKTREE_ROOT}"

# --- Guardrails ----------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' is not on PATH. Install uv first." >&2
  exit 1
fi

# Per-step API key checks. Called from the relevant runner functions rather
# than at top level so OpenAI-only steps don't demand ANTHROPIC_API_KEY and
# vice versa.
require_anthropic_key() {
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "ERROR: ANTHROPIC_API_KEY is not set. Export it before running this step." >&2
    exit 1
  fi
}

require_openai_key() {
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "ERROR: OPENAI_API_KEY is not set. Export it before running this step." >&2
    exit 1
  fi
}

# --- Shared config -------------------------------------------------------------
PROVIDER="anthropic"
MODEL="claude-sonnet-4-5-20250929"
SUMMARY_MODEL="claude-haiku-4-5"
JUDGE_MODEL="claude-haiku-4-5"
ARMS="baseline,headroom_default,summary_prompt"

# LongMemEval headline-run params (from research/2026-04-08-compaction-compare-progress.md)
CONTEXT_WINDOW=128000
TRIGGER_FILL=0.55
CHUNK_TOKEN_SIZE=15000
KEEP_RECENT=2
MAX_TOKENS=256

OUT_ROOT="eval_results/compaction_compare"

# ==============================================================================
# LongMemEval steps (work today, no patch needed)
# ==============================================================================

run_smoke() {
  echo ">>> LongMemEval smoke (2 cases, no judge)"
  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 2 \
    --arms baseline,headroom_default \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --threshold 50000 \
    --no-judge \
    -o "/tmp/cc_smoke_longmemeval_$(date +%s)"
}

run_temporal_rerun() {
  local out="${OUT_ROOT}/longmemeval/anthropic/by_type/temporal-reasoning_rerun"
  echo ">>> Temporal-reasoning baseline rerun → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 30 \
    --question-type temporal-reasoning \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --summary-model "${SUMMARY_MODEL}" \
    --judge-model "${JUDGE_MODEL}" \
    --threshold 50000 \
    --model-context-window "${CONTEXT_WINDOW}" \
    --trigger-fill "${TRIGGER_FILL}" \
    --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
    --keep-recent "${KEEP_RECENT}" \
    --max-tokens "${MAX_TOKENS}" \
    -o "${out}"
}

run_n150_mixed() {
  local out="${OUT_ROOT}/longmemeval/anthropic/n150"
  echo ">>> Mixed n=150 headline rerun → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 150 \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --summary-model "${SUMMARY_MODEL}" \
    --judge-model "${JUDGE_MODEL}" \
    --threshold 50000 \
    --model-context-window "${CONTEXT_WINDOW}" \
    --trigger-fill "${TRIGGER_FILL}" \
    --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
    --keep-recent "${KEEP_RECENT}" \
    --max-tokens "${MAX_TOKENS}" \
    -o "${out}"
}

run_threshold_sweep() {
  for T in 25000 50000 100000; do
    local out="${OUT_ROOT}/longmemeval/anthropic/threshold_sweep/t${T}"
    echo ">>> Threshold sweep T=${T} → ${out}"
    uv run python -m headroom.evals compaction-compare \
      --dataset longmemeval \
      -n 50 \
      --arms "${ARMS}" \
      --provider "${PROVIDER}" \
      --model "${MODEL}" \
      --summary-model "${SUMMARY_MODEL}" \
      --judge-model "${JUDGE_MODEL}" \
      --threshold "${T}" \
      --model-context-window "${CONTEXT_WINDOW}" \
      --trigger-fill "${TRIGGER_FILL}" \
      --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
      --keep-recent "${KEEP_RECENT}" \
      --max-tokens "${MAX_TOKENS}" \
      -o "${out}"
  done
}

run_aggregate() {
  echo ">>> Aggregating per-type results into cross_type_report.md"
  uv run python research/aggregate_by_type.py
}

# ==============================================================================
# Cross-dataset smokes (REQUIRE runner patch, but fail cheaply if not patched)
# ==============================================================================
#
# These all use -n 2 and --no-judge so if the runner crashes on a non-LongMemEval
# context shape, you lose seconds, not dollars. Run the patch first (see BLOCKER
# section) then use these to verify before the full runs.

run_smoke_longbench() {
  echo ">>> LongBench v1 suite smoke (2 cases, no judge)"
  uv run python -m headroom.evals compaction-compare \
    --dataset longbench_v1_suite \
    -n 2 \
    --arms baseline,headroom_default \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --threshold 50000 \
    --max-tokens "${MAX_TOKENS}" \
    --no-judge \
    -o "/tmp/cc_smoke_longbench_$(date +%s)"
}

run_smoke_hotpotqa() {
  echo ">>> HotpotQA smoke (2 cases, no judge)"
  uv run python -m headroom.evals compaction-compare \
    --dataset hotpotqa \
    -n 2 \
    --arms baseline,headroom_default \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --threshold 5000 \
    --max-tokens "${MAX_TOKENS}" \
    --no-judge \
    -o "/tmp/cc_smoke_hotpotqa_$(date +%s)"
}

run_smoke_narrativeqa() {
  echo ">>> NarrativeQA smoke (2 cases, no judge)"
  uv run python -m headroom.evals compaction-compare \
    --dataset narrativeqa \
    -n 2 \
    --arms baseline,headroom_default \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --threshold 50000 \
    --max-tokens "${MAX_TOKENS}" \
    --no-judge \
    -o "/tmp/cc_smoke_narrativeqa_$(date +%s)"
}

run_smoke_natural_questions() {
  echo ">>> Natural Questions smoke (2 cases, no judge)"
  uv run python -m headroom.evals compaction-compare \
    --dataset natural_questions \
    -n 2 \
    --arms baseline,headroom_default \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --threshold 5000 \
    --max-tokens "${MAX_TOKENS}" \
    --no-judge \
    -o "/tmp/cc_smoke_natural_questions_$(date +%s)"
}

# ==============================================================================
# Arm-specific: openai_compact_v2 smoke against the live OpenAI Responses API
# ==============================================================================
#
# Probes the openai_compact_v2 arm on gpt-5.4 with 2 LongMemEval cases and
# --no-judge. The runner passes `context_management=[{...}]` through the
# SDK's extra_body escape hatch because openai==2.15.0 doesn't type the
# field yet. As of 2026-04-09 this is UNVERIFIED end-to-end — it has only
# been tested against fakes plus two layers of live-server error iteration
# (see research/2026-04-09-streamlit-reproduction-comparison.md § 4.1.b).
#
# If the run errors, inspect the exact server response with:
#   cat /tmp/cc_smoke_openai_compact_v2/report.json | python3 -c \
#     'import sys,json;d=json.load(sys.stdin);[print(r.get("case_id"),"→",r.get("error")) for r in d["results"]["openai_compact_v2"]]'

run_openai_compact_v2_smoke() {
  require_openai_key
  local out="/tmp/cc_smoke_openai_compact_v2"
  echo ">>> openai_compact_v2 smoke (2 cases, no judge, live OpenAI API) → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 2 \
    --arms openai_compact_v2 \
    --provider openai \
    --model gpt-5.4 \
    --openai-compact-v2-trigger 60000 \
    --openai-compact-v2-max-output-tokens 2048 \
    --no-judge \
    -o "${out}"
}

# Head-to-head: run anthropic_compact_v2 and openai_compact_v2 back-to-back on
# the same 2 LongMemEval cases so the outputs can be diffed manually. The
# CompactionCompareDriver validates that every arm in a single invocation
# belongs to the same provider (provider=anthropic rejects openai arms and
# vice versa), so we run them as two separate CLI invocations with matching
# -n 2 and the same dataset ordering. LongMemEval is deterministic on the
# first N cases, so both invocations see the same two cases.
#
# The goal of this step is to test the "commute case" signal from the 2026-04-09
# smoke: openai_compact_v2 answered the commute question correctly while
# anthropic_compact_v2 is documented to fail on it. This head-to-head pins
# that down on the exact same inputs. Do NOT generalise from n=2 — scale to
# n≥20 with --judge before treating any claim as real.
run_compact_v2_headhead_smoke() {
  require_anthropic_key
  require_openai_key
  local anthropic_out="/tmp/cc_headhead_anthropic_compact_v2"
  local openai_out="/tmp/cc_headhead_openai_compact_v2"

  echo ">>> head-to-head smoke: anthropic_compact_v2 vs openai_compact_v2"
  echo ">>> shared dataset: longmemeval, first 2 cases, no judge"
  echo

  echo ">>> [1/2] anthropic_compact_v2 on claude-sonnet-4-6 → ${anthropic_out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 2 \
    --arms anthropic_compact_v2 \
    --provider anthropic \
    --model claude-sonnet-4-6 \
    --compact-v2-trigger 60000 \
    --compact-v2-max-tokens 2048 \
    --no-judge \
    -o "${anthropic_out}"

  echo
  echo ">>> [2/2] openai_compact_v2 on gpt-5.4 → ${openai_out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 2 \
    --arms openai_compact_v2 \
    --provider openai \
    --model gpt-5.4 \
    --openai-compact-v2-trigger 60000 \
    --openai-compact-v2-max-output-tokens 2048 \
    --no-judge \
    -o "${openai_out}"

  echo
  echo ">>> head-to-head done. diff the two per-case answers with:"
  echo "    python3 -c \"
import json
a = json.load(open('${anthropic_out}/report.json'))['results']['anthropic_compact_v2']
o = json.load(open('${openai_out}/report.json'))['results']['openai_compact_v2']
for ar, orr in zip(a, o):
    print('case:', ar['case_id'])
    print('  anthropic:', (ar.get('answer') or '')[:150])
    print('  openai:   ', (orr.get('answer') or '')[:150])
    print('  anthropic_latency_ms:', round(ar.get('latency_ms',0)))
    print('  openai_latency_ms:   ', round(orr.get('latency_ms',0)))
    print('  anthropic_n_compactions:', ar.get('n_compactions'))
    print('  openai_n_compactions:   ', orr.get('n_compactions'))
    print()
\""
}

# ==============================================================================
# Cross-dataset full runs (REQUIRE runner patch, expensive)
# ==============================================================================

run_longbench_v1_suite() {
  local out="${OUT_ROOT}/longbench_v1_suite/anthropic/n100"
  echo ">>> LongBench v1 suite n=100 → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset longbench_v1_suite \
    -n 100 \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --summary-model "${SUMMARY_MODEL}" \
    --judge-model "${JUDGE_MODEL}" \
    --threshold 50000 \
    --model-context-window "${CONTEXT_WINDOW}" \
    --trigger-fill "${TRIGGER_FILL}" \
    --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
    --keep-recent "${KEEP_RECENT}" \
    --max-tokens "${MAX_TOKENS}" \
    -o "${out}"
}

run_narrativeqa() {
  local out="${OUT_ROOT}/narrativeqa/anthropic/n100"
  echo ">>> NarrativeQA n=100 → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset narrativeqa \
    -n 100 \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --summary-model "${SUMMARY_MODEL}" \
    --judge-model "${JUDGE_MODEL}" \
    --threshold 50000 \
    --model-context-window "${CONTEXT_WINDOW}" \
    --trigger-fill "${TRIGGER_FILL}" \
    --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
    --keep-recent "${KEEP_RECENT}" \
    --max-tokens "${MAX_TOKENS}" \
    -o "${out}"
}

run_hotpotqa() {
  local out="${OUT_ROOT}/hotpotqa/anthropic/n100"
  echo ">>> HotpotQA n=100 → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset hotpotqa \
    -n 100 \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --summary-model "${SUMMARY_MODEL}" \
    --judge-model "${JUDGE_MODEL}" \
    --threshold 5000 \
    --model-context-window "${CONTEXT_WINDOW}" \
    --trigger-fill "${TRIGGER_FILL}" \
    --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
    --keep-recent "${KEEP_RECENT}" \
    --max-tokens "${MAX_TOKENS}" \
    -o "${out}"
}

run_natural_questions() {
  local out="${OUT_ROOT}/natural_questions/anthropic/n100"
  echo ">>> Natural Questions n=100 → ${out}"
  uv run python -m headroom.evals compaction-compare \
    --dataset natural_questions \
    -n 100 \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --summary-model "${SUMMARY_MODEL}" \
    --judge-model "${JUDGE_MODEL}" \
    --threshold 5000 \
    --model-context-window "${CONTEXT_WINDOW}" \
    --trigger-fill "${TRIGGER_FILL}" \
    --chunk-token-size "${CHUNK_TOKEN_SIZE}" \
    --keep-recent "${KEEP_RECENT}" \
    --max-tokens "${MAX_TOKENS}" \
    -o "${out}"
}

# ==============================================================================
# Dispatch
# ==============================================================================

STEP="${1:-}"

# Key-requirement pre-dispatch: every step uses ANTHROPIC_API_KEY except
# openai_compact_v2_smoke (which uses OPENAI_API_KEY and is gated inside its
# own runner function) and the pure-local steps (aggregate, help, empty).
case "${STEP}" in
  openai_compact_v2_smoke|aggregate|""|help|-h|--help) ;;
  compact_v2_headhead_smoke) ;;  # checks both keys inside the runner function
  *) require_anthropic_key ;;
esac

case "${STEP}" in
  # sanity
  smoke)                       run_smoke ;;

  # LongMemEval (work today)
  temporal_rerun)              run_temporal_rerun ;;
  n150_mixed)                  run_n150_mixed ;;
  threshold_sweep)             run_threshold_sweep ;;
  aggregate)                   run_aggregate ;;
  all_longmemeval)
    run_temporal_rerun
    run_n150_mixed
    run_threshold_sweep
    run_aggregate
    ;;

  # cross-dataset smokes
  smoke_longbench)             run_smoke_longbench ;;
  smoke_hotpotqa)              run_smoke_hotpotqa ;;
  smoke_narrativeqa)           run_smoke_narrativeqa ;;
  smoke_natural_questions)     run_smoke_natural_questions ;;
  all_cross_dataset_smokes)
    run_smoke_longbench
    run_smoke_hotpotqa
    run_smoke_narrativeqa
    run_smoke_natural_questions
    ;;

  # arm-specific (live OpenAI API)
  openai_compact_v2_smoke)     run_openai_compact_v2_smoke ;;
  compact_v2_headhead_smoke)   run_compact_v2_headhead_smoke ;;

  # cross-dataset full runs
  longbench_v1_suite)          run_longbench_v1_suite ;;
  narrativeqa)                 run_narrativeqa ;;
  hotpotqa)                    run_hotpotqa ;;
  natural_questions)           run_natural_questions ;;
  all_cross_dataset)
    run_longbench_v1_suite
    run_narrativeqa
    run_hotpotqa
    run_natural_questions
    ;;

  everything)
    run_temporal_rerun
    run_n150_mixed
    run_threshold_sweep
    run_aggregate
    run_smoke_longbench
    run_smoke_hotpotqa
    run_smoke_narrativeqa
    run_smoke_natural_questions
    run_longbench_v1_suite
    run_narrativeqa
    run_hotpotqa
    run_natural_questions
    ;;

  ""|help|-h|--help)
    grep -E '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    echo "Unknown step: ${STEP}" >&2
    echo "Run '$0 --help' to see available steps." >&2
    exit 2
    ;;
esac

echo ">>> Done: ${STEP}"

# ==============================================================================
# BLOCKER — cross-dataset steps require a runner patch
# ==============================================================================
#
# Running any cross-dataset step (smoke or full) against the CURRENT runners will
# crash inside BaselineRunner, HeadroomDefaultRunner, and SummaryPromptRunner,
# because all three call _flatten_haystack(case.context), which does:
#
#     data = json.loads(context)
#     sessions = data.get("haystack_sessions", [])
#
# That's a LongMemEval-only shape. HotpotQA, LongBench, NarrativeQA, and Natural
# Questions all produce plain-string contexts, so json.loads will raise on the
# first case.
#
# Affected files:
#   headroom/evals/runners/direct_runners.py:29   (_flatten_haystack)
#   headroom/evals/runners/summary_prompt.py:62   (_flatten_haystack)
#
# Fix (both files): when json.loads raises, OR when the parsed object has no
# "haystack_sessions" key, return the raw context string unchanged. Add a small
# regression test that feeds a non-JSON string in and asserts it round-trips.
#
# After patching, the right sequence is:
#   1. ./research/run_compaction_compare_next.sh all_cross_dataset_smokes
#      (should finish in a few minutes, ~$0, proves the patch holds on every
#      dataset shape)
#   2. ./research/run_compaction_compare_next.sh all_cross_dataset
#      (the real $80–130 sweep)
#
# Ask Claude to make the patch when you're ready: "patch _flatten_haystack in both
# runners to fall back to raw strings and add a regression test."
