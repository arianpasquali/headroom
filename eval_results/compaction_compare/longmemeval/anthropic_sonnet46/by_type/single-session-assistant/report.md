# Compaction Compare — LongMemEval_longmemeval_s_cleaned_single-session-assistant

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 63.3% | 7689ms | 7689ms | $0.3785 | 0.0 | 0 |
| headroom_default | 30 | 55.2% | +30.0% | 93.3% | 4936ms | 4936ms | $0.1707 | 0.0 | 0 |
| anthropic_compact_v2 | 30 | 99.6% | +20.0% | 83.3% | 10814ms | 10814ms | $0.3832 | 1.0 | 0 |
| dumb_truncation_last_n | 30 | 54.0% | -10.0% | 53.3% | 5979ms | 5979ms | $0.1758 | 0.0 | 0 |
| random_chunk_drop | 30 | 53.8% | -10.0% | 53.3% | 6353ms | 6353ms | $0.1768 | 0.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-assistant |
|---|---|
| baseline | 63.3% |
| headroom_default | 93.3% |
| anthropic_compact_v2 | 83.3% |
| dumb_truncation_last_n | 53.3% |
| random_chunk_drop | 53.3% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
