# Compaction Compare — LongMemEval_longmemeval_s_cleaned_single-session-user

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-6
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, anthropic_compact_v2
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 wall-clock | p50 user-visible | mean $/case | mean compactions | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 50 | 0.0% | +0.0% | 40.0% | 6754ms | 6754ms | $0.3756 | 0.0 | 0 |
| headroom_default | 50 | 54.2% | +42.0% | 82.0% | 4667ms | 4667ms | $0.1727 | 0.0 | 0 |
| anthropic_compact_v2 | 50 | 99.7% | +14.0% | 54.0% | 8660ms | 8660ms | $0.3792 | 1.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-user |
|---|---|
| baseline | 40.0% |
| headroom_default | 82.0% |
| anthropic_compact_v2 | 54.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-6`
- Summary model: `claude-haiku-4-5`
