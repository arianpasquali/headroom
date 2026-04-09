# Compaction Compare — LongMemEval_longmemeval_s_cleaned_single-session-user

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 50 | 0.0% | +0.0% | 38.0% | 6286ms | 6286ms | $0.3757 | 0.0 | 0 |
| headroom_default | 50 | 54.2% | +46.0% | 84.0% | 4615ms | 4615ms | $0.1727 | 0.0 | 0 |
| anthropic_compact_v2 | 50 | 99.7% | +16.0% | 54.0% | 8312ms | 8312ms | $0.3791 | 1.0 | 0 |
| dumb_truncation_last_n | 50 | 54.0% | -10.0% | 28.0% | 3707ms | 3707ms | $0.1734 | 0.0 | 0 |
| random_chunk_drop | 50 | 53.8% | -16.0% | 22.0% | 4155ms | 4155ms | $0.1754 | 0.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-user |
|---|---|
| baseline | 38.0% |
| headroom_default | 84.0% |
| anthropic_compact_v2 | 54.0% |
| dumb_truncation_last_n | 28.0% |
| random_chunk_drop | 22.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
