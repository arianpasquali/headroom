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
| baseline | 150 | 0.0% | +0.0% | 32.7% | 7181ms | 0.0 | 0 |
| headroom_default | 150 | 54.8% | +20.0% | 52.7% | 5395ms | 0.0 | 0 |
| summary_prompt | 150 | 39.5% | -2.0% | 30.7% | 9261ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-user | multi-session | single-session-preference |
|---|---|---|---|
| baseline | 52.9% | 16.1% | 11.1% |
| headroom_default | 78.6% | 32.3% | 22.2% |
| summary_prompt | 47.1% | 17.7% | 11.1% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`
