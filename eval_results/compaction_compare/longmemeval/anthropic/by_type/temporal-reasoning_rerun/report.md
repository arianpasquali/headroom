# Compaction Compare — LongMemEval_longmemeval_s_cleaned_temporal-reasoning

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-5-20250929
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, summary_prompt
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 latency | mean compactions | errors |
|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 0.0% | 7924ms | 0.0 | 0 |
| headroom_default | 30 | 55.0% | +6.7% | 6.7% | 6424ms | 0.0 | 0 |
| summary_prompt | 30 | 39.5% | +0.0% | 0.0% | 8812ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | temporal-reasoning |
|---|---|
| baseline | 0.0% |
| headroom_default | 6.7% |
| summary_prompt | 0.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`
