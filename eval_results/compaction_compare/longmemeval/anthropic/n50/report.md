# Compaction Compare — LongMemEval_longmemeval_s_cleaned

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-5-20250929
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, summary_prompt
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 latency | mean compactions | errors |
|---|---|---|---|---|---|---|---|
| baseline | 50 | 0.0% | +0.0% | 52.0% | 7100ms | 0.0 | 0 |
| headroom_default | 50 | 54.3% | +22.0% | 74.0% | 4375ms | 0.0 | 0 |
| summary_prompt | 50 | 39.5% | -2.0% | 50.0% | 8489ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-user |
|---|---|
| baseline | 52.0% |
| headroom_default | 74.0% |
| summary_prompt | 50.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`
