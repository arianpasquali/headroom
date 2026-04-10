# Compaction Compare — LongMemEval_longmemeval_s_cleaned_temporal-reasoning

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 0.0% | 6970ms | 6970ms | $0.3755 | 0.0 | 0 |
| headroom_default | 30 | 55.0% | +6.7% | 6.7% | 5201ms | 5201ms | $0.1704 | 0.0 | 0 |
| anthropic_compact_v2 | 30 | 99.6% | +0.0% | 0.0% | 10076ms | 10076ms | $0.3805 | 1.0 | 0 |
| dumb_truncation_last_n | 30 | 54.0% | +0.0% | 0.0% | 3930ms | 3930ms | $0.1733 | 0.0 | 0 |
| random_chunk_drop | 30 | 54.0% | +3.3% | 3.3% | 3947ms | 3947ms | $0.1738 | 0.0 | 0 |

## Per Question Type Breakdown

| arm | temporal-reasoning |
|---|---|
| baseline | 0.0% |
| headroom_default | 6.7% |
| anthropic_compact_v2 | 0.0% |
| dumb_truncation_last_n | 0.0% |
| random_chunk_drop | 3.3% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
