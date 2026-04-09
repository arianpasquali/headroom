# Compaction Compare — LongMemEval_longmemeval_s_cleaned_single-session-preference

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 26.7% | 10447ms | 10447ms | $0.3799 | 0.0 | 0 |
| headroom_default | 30 | 54.7% | +16.7% | 43.3% | 8968ms | 8968ms | $0.1748 | 0.0 | 0 |
| anthropic_compact_v2 | 30 | 99.5% | -20.0% | 6.7% | 14220ms | 14220ms | $0.3856 | 1.0 | 0 |
| dumb_truncation_last_n | 30 | 54.0% | +3.3% | 30.0% | 8698ms | 8698ms | $0.1772 | 0.0 | 0 |
| random_chunk_drop | 30 | 53.9% | -6.7% | 20.0% | 9164ms | 9164ms | $0.1783 | 0.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-preference |
|---|---|
| baseline | 26.7% |
| headroom_default | 43.3% |
| anthropic_compact_v2 | 6.7% |
| dumb_truncation_last_n | 30.0% |
| random_chunk_drop | 20.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
