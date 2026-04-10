# Compaction Compare — LongMemEval_longmemeval_s_cleaned_multi-session

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 6.7% | 5589ms | 5589ms | $0.3746 | 0.0 | 0 |
| headroom_default | 30 | 55.8% | +26.7% | 33.3% | 5767ms | 5767ms | $0.1674 | 0.0 | 0 |
| anthropic_compact_v2 | 30 | 99.6% | +6.7% | 13.3% | 9083ms | 9083ms | $0.3790 | 1.0 | 0 |
| dumb_truncation_last_n | 30 | 54.0% | -3.3% | 3.3% | 4166ms | 4166ms | $0.1733 | 0.0 | 0 |
| random_chunk_drop | 30 | 53.9% | -6.7% | 0.0% | 4532ms | 4532ms | $0.1737 | 0.0 | 0 |

## Per Question Type Breakdown

| arm | multi-session |
|---|---|
| baseline | 6.7% |
| headroom_default | 33.3% |
| anthropic_compact_v2 | 13.3% |
| dumb_truncation_last_n | 3.3% |
| random_chunk_drop | 0.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
