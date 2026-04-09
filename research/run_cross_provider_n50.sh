#!/usr/bin/env bash
#
# Cross-provider N=50 head-to-head for RES-333 sync.
#
# Runs two sequential sweeps on the SAME 50 LongMemEval single-session-user cases:
#
#   1. Anthropic side (Sonnet 4.6), 5 arms:
#        baseline, headroom_default, anthropic_compact_v2,
#        dumb_truncation_last_n, random_chunk_drop
#
#   2. OpenAI side (gpt-5.4), 3 arms:
#        baseline, headroom_default, openai_compact_v2
#
# The driver rejects mixed-provider arm lists, so this is two separate CLI
# invocations. Results land in parallel subdirectories:
#   eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50_5arm/
#   eval_results/compaction_compare/longmemeval/openai_gpt54/n50_3arm/
#
# Preconditions:
#   - ANTHROPIC_API_KEY in env (from .env)
#   - OPENAI_API_KEY in env OR ~/.openai-key file present
#
# Cost estimate: ~$65 Anthropic + ~$40–80 OpenAI = ~$105–145 total
# Wall-clock: ~30–45 min Anthropic + ~60–120 min OpenAI = ~1.5–2.5 hours
#
# Usage:
#   ./research/run_cross_provider_n50.sh              # run both sides
#   ./research/run_cross_provider_n50.sh anthropic    # anthropic only
#   ./research/run_cross_provider_n50.sh openai       # openai only

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${WORKTREE_ROOT}"

# --- Load OPENAI_API_KEY from ~/.openai-key if not already set --------------
# The file may be a raw key OR a shell-sourceable line like
# `echo export OPENAI_API_KEY=sk-...`. Handle both: if we see an OPENAI_API_KEY=
# substring, extract what comes after; otherwise treat the whole file as the key.
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ -f "${HOME}/.openai-key" ]]; then
    raw_key_file="$(cat "${HOME}/.openai-key")"
    if [[ "${raw_key_file}" == *"OPENAI_API_KEY="* ]]; then
      OPENAI_API_KEY="$(printf '%s' "${raw_key_file}" | sed -n 's/.*OPENAI_API_KEY=//p' | tr -d '[:space:]')"
    else
      OPENAI_API_KEY="$(printf '%s' "${raw_key_file}" | tr -d '[:space:]')"
    fi
    export OPENAI_API_KEY
  fi
fi

# --- Guardrails --------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' is not on PATH." >&2
  exit 1
fi

SIDE="${1:-both}"
LOG_DIR="/tmp/cross_provider_n50_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${LOG_DIR}"

echo ">>> Cross-provider N=50 head-to-head starting"
echo ">>> Side: ${SIDE}"
echo ">>> Log dir: ${LOG_DIR}"
echo ">>> Start: $(date)"
echo ""

# ==============================================================================
# Anthropic — Sonnet 4.6 5-arm N=50
# ==============================================================================

run_anthropic() {
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "ERROR: ANTHROPIC_API_KEY not set. Source .env first." >&2
    return 1
  fi

  local out="eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50_5arm"
  local log="${LOG_DIR}/anthropic_5arm.log"
  mkdir -p "${out}"

  echo ">>> [$(date '+%H:%M:%S')] Starting Anthropic 5-arm N=50 on Sonnet 4.6"
  echo ">>>   Arms: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop"
  echo ">>>   Output: ${out}"
  echo ">>>   Log: ${log}"

  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 50 \
    --question-type single-session-user \
    --arms baseline,headroom_default,anthropic_compact_v2,dumb_truncation_last_n,random_chunk_drop \
    --provider anthropic \
    --model claude-sonnet-4-6 \
    --max-tokens 512 \
    --compact-v2-trigger 60000 \
    --compact-v2-max-tokens 1500 \
    --floor-target-compression-ratio 0.54 \
    --floor-random-chunk-token-size 2000 \
    --judge-model claude-haiku-4-5 \
    -o "${out}" \
    > "${log}" 2>&1

  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    echo ">>> [$(date '+%H:%M:%S')] Anthropic side FAILED (exit ${exit_code}). See ${log}"
    return ${exit_code}
  fi

  echo ">>> [$(date '+%H:%M:%S')] Anthropic side done. Summary:"
  if [[ -f "${out}/summary.txt" ]]; then
    sed 's/^/    /' "${out}/summary.txt"
  fi
  echo ""
}

# ==============================================================================
# OpenAI — gpt-5.4 3-arm N=50
# ==============================================================================

run_openai() {
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "ERROR: OPENAI_API_KEY not set (checked env and ~/.openai-key)." >&2
    return 1
  fi

  local out="eval_results/compaction_compare/longmemeval/openai_gpt54/n50_3arm"
  local log="${LOG_DIR}/openai_3arm.log"
  mkdir -p "${out}"

  echo ">>> [$(date '+%H:%M:%S')] Starting OpenAI 3-arm N=50 on gpt-5.4"
  echo ">>>   Arms: baseline, headroom_default, openai_compact_v2"
  echo ">>>   Output: ${out}"
  echo ">>>   Log: ${log}"
  echo ">>>   NOTE: openai_compact_v2 latency ~19.3s/case from smoke — ~16 min just for that arm"

  uv run python -m headroom.evals compaction-compare \
    --dataset longmemeval \
    -n 50 \
    --question-type single-session-user \
    --arms baseline,headroom_default,openai_compact_v2 \
    --provider openai \
    --model gpt-5.4 \
    --max-tokens 512 \
    --openai-compact-v2-trigger 60000 \
    --openai-compact-v2-max-output-tokens 1500 \
    --judge-model claude-haiku-4-5 \
    -o "${out}" \
    > "${log}" 2>&1

  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    echo ">>> [$(date '+%H:%M:%S')] OpenAI side FAILED (exit ${exit_code}). See ${log}"
    return ${exit_code}
  fi

  echo ">>> [$(date '+%H:%M:%S')] OpenAI side done. Summary:"
  if [[ -f "${out}/summary.txt" ]]; then
    sed 's/^/    /' "${out}/summary.txt"
  fi
  echo ""
}

# ==============================================================================
# Dispatch
# ==============================================================================

case "${SIDE}" in
  anthropic) run_anthropic ;;
  openai)    run_openai ;;
  both)
    run_anthropic
    anth_exit=$?
    if [[ ${anth_exit} -ne 0 ]]; then
      echo ">>> Anthropic side failed. Continuing with OpenAI side anyway."
    fi
    run_openai
    ;;
  *)
    echo "Usage: $0 [anthropic|openai|both]" >&2
    exit 2
    ;;
esac

echo ">>> [$(date '+%H:%M:%S')] Cross-provider N=50 sweep finished."
echo ">>> Logs: ${LOG_DIR}"
