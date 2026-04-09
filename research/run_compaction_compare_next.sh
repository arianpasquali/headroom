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
# Convenience
#   everything                   all_longmemeval + all_cross_dataset_smokes + all_cross_dataset.
#                                Total cost ~$100–150. Only run this if you know what you're doing.
#
# ─── Preconditions ────────────────────────────────────────────────────────────
#
#   - ANTHROPIC_API_KEY exported.
#   - uv installed and on PATH.
#   - This script lives inside the feat/compaction-compare worktree; it cd's to
#     the worktree root on launch, so you can run it from anywhere.

set -euo pipefail

# --- Locate the worktree root regardless of caller cwd -------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${WORKTREE_ROOT}"

# --- Guardrails ----------------------------------------------------------------
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set. Export it before running." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' is not on PATH. Install uv first." >&2
  exit 1
fi

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
