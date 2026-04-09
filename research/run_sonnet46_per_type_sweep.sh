#!/usr/bin/env bash
#
# Sonnet 4.6 per-type sweep — 5 arms × 5 types × N=30
#
# Generalization evidence for the 2026-04-09 cross-provider headline. The
# headline Sonnet 4.6 run (anthropic_sonnet46/n50_5arm/) covers
# single-session-user only; this sweep covers the other 5 LongMemEval
# question types so we can present a full 6-type Sonnet 4.6 table for the
# RES-333 sync.
#
# Scope:
#   Arms:  baseline, headroom_default, anthropic_compact_v2,
#          dumb_truncation_last_n, random_chunk_drop
#   Types: multi-session, temporal-reasoning, knowledge-update,
#          single-session-assistant, single-session-preference
#   N:     30 per type per arm
#   Model: claude-sonnet-4-6
#
# Total API calls: 5 types × 5 arms × 30 cases = 750 + 750 judge calls
# Estimated cost: ~$192 across all 5 types
# Estimated wall-clock: ~2 hours unattended
#
# Output per type:
#   eval_results/compaction_compare/longmemeval/anthropic_sonnet46/by_type/<type>/
#
# Design notes:
#
# - Each type runs as a SEPARATE CLI invocation. If one type hangs or
#   errors, the others still complete — isolation prevents a single bad
#   case from killing the whole sweep. This was the lesson from the
#   earlier 4-arm attempt that hung on anthropic_session_memory.
# - Logs land in /tmp/sonnet46_per_type_<timestamp>/<type>.log for each
#   type independently, so post-hoc debugging is per-type too.
# - The script prints summary.txt contents after each type completes, so
#   running it in the foreground or via `tee` gives you live progress.
# - No judge parallelism — we let the driver's judge pass run fully per
#   type before moving on. Simpler and deterministic.
#
# Usage:
#   ./research/run_sonnet46_per_type_sweep.sh              # run all 5 types
#   ./research/run_sonnet46_per_type_sweep.sh <type>       # run one specific type

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${WORKTREE_ROOT}"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY not set. Source .env first." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' is not on PATH." >&2
  exit 1
fi

PROVIDER="anthropic"
MODEL="claude-sonnet-4-6"
JUDGE_MODEL="claude-haiku-4-5"
ARMS="baseline,headroom_default,anthropic_compact_v2,dumb_truncation_last_n,random_chunk_drop"
OUT_ROOT="eval_results/compaction_compare/longmemeval/anthropic_sonnet46/by_type"
LOG_DIR="/tmp/sonnet46_per_type_$(date +%Y%m%d_%H%M%S)"

mkdir -p "${LOG_DIR}"

echo ">>> Sonnet 4.6 per-type sweep starting"
echo ">>> Arms: ${ARMS}"
echo ">>> Log dir: ${LOG_DIR}"
echo ">>> Output root: ${OUT_ROOT}"
echo ">>> Start time: $(date)"
echo ""

run_one_type() {
  local qtype="$1"
  local out="${OUT_ROOT}/${qtype}"
  local log="${LOG_DIR}/${qtype}.log"

  echo ">>> [$(date '+%H:%M:%S')] Starting ${qtype}"
  echo ">>>   Output: ${out}"
  echo ">>>   Log: ${log}"
  mkdir -p "${out}"

  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 30 \
    --question-type "${qtype}" \
    --arms "${ARMS}" \
    --provider "${PROVIDER}" \
    --model "${MODEL}" \
    --max-tokens 512 \
    --compact-v2-trigger 60000 \
    --compact-v2-max-tokens 1500 \
    --floor-target-compression-ratio 0.54 \
    --floor-random-chunk-token-size 2000 \
    --judge-model "${JUDGE_MODEL}" \
    -o "${out}" \
    > "${log}" 2>&1

  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    echo ">>> [$(date '+%H:%M:%S')] ${qtype} FAILED (exit ${exit_code}). Log: ${log}"
    echo ">>>   Continuing with next type."
  else
    echo ">>> [$(date '+%H:%M:%S')] ${qtype} DONE. Summary:"
    if [[ -f "${out}/summary.txt" ]]; then
      sed 's/^/    /' "${out}/summary.txt"
    fi
  fi
  echo ""
}

TYPES=(
  "multi-session"
  "temporal-reasoning"
  "knowledge-update"
  "single-session-assistant"
  "single-session-preference"
)

if [[ $# -ge 1 ]]; then
  run_one_type "$1"
else
  for t in "${TYPES[@]}"; do
    run_one_type "${t}"
  done
fi

echo ">>> [$(date '+%H:%M:%S')] Sonnet 4.6 per-type sweep finished."
echo ">>> Logs: ${LOG_DIR}"
echo ">>> Results: ${OUT_ROOT}"
echo ""
echo ">>> Final summaries per type:"
for t in "${TYPES[@]}"; do
  s="${OUT_ROOT}/${t}/summary.txt"
  if [[ -f "${s}" ]]; then
    echo ""
    echo "  ${t}:"
    sed 's/^/    /' "${s}"
  fi
done

echo ""
echo ">>> Next step: run research/aggregate_by_type.py to build the cross-type report"
