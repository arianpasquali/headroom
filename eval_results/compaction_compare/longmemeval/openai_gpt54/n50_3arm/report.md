# Compaction Compare — LongMemEval_longmemeval_s_cleaned_single-session-user

## Configuration

- **Provider**: openai
- **Model**: gpt-5.4
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, openai_compact_v2
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 50 | 0.0% | +0.0% | 98.0% | 7096ms | 7096ms | $0.2836 | 0.0 | 0 |
| headroom_default | 50 | 54.2% | +0.0% | 98.0% | 4038ms | 4038ms | $0.1301 | 0.0 | 0 |
| openai_compact_v2 | 50 | 1.1% | +0.0% | 98.0% | 14288ms | 14288ms | $0.2807 | 1.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-user |
|---|---|
| baseline | 98.0% |
| headroom_default | 98.0% |
| openai_compact_v2 | 98.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `gpt-5.4`
- Summary model: `claude-haiku-4-5`
