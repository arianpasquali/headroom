# Compaction Compare — LongMemEval_longmemeval_s_cleaned_knowledge-update

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2, dumb_truncation_last_n, random_chunk_drop
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 50.0% | 5936ms | 5936ms | $0.3753 | 0.0 | 0 |
| headroom_default | 30 | 55.3% | +20.0% | 70.0% | 3605ms | 3605ms | $0.1685 | 0.0 | 0 |
| anthropic_compact_v2 | 30 | 99.7% | +23.3% | 73.3% | 7617ms | 7617ms | $0.3787 | 1.0 | 0 |
| dumb_truncation_last_n | 30 | 54.0% | +10.0% | 60.0% | 3386ms | 3386ms | $0.1728 | 0.0 | 0 |
| random_chunk_drop | 30 | 54.2% | -16.7% | 33.3% | 3728ms | 3728ms | $0.1733 | 0.0 | 0 |

## Per Question Type Breakdown

| arm | knowledge-update |
|---|---|
| baseline | 50.0% |
| headroom_default | 70.0% |
| anthropic_compact_v2 | 73.3% |
| dumb_truncation_last_n | 60.0% |
| random_chunk_drop | 33.3% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
