# Compaction Compare — LongMemEval cross-type meta-report

Aggregates the headline N=50 single-session-user run with the Phase 2
N=30 sweeps across the other 5 LongMemEval question types. Built by
`research/aggregate_by_type.py` from the per-type `scored_report.json` files.

## Quality (correct rate per question type)

| arm | single-session-user | multi-session | temporal-reasoning | knowledge-update | single-session-assistant | single-session-preference | grand mean |
|---|---|---|---|---|---|---|---|
| baseline | 52.0% | 16.7% | 0.0% | 46.7% | 56.7% | 10.0% | 30.3% |
| headroom_default | 74.0% | 30.0% | 6.7% | 70.0% | 93.3% | 33.3% | 51.2% |
| summary_prompt | 50.0% | 20.0% | 0.0% | 50.0% | 70.0% | 23.3% | 35.6% |

## Δ quality vs baseline (per question type)

| arm | single-session-user | multi-session | temporal-reasoning | knowledge-update | single-session-assistant | single-session-preference | grand mean |
|---|---|---|---|---|---|---|---|
| baseline (reference) | — | — | — | — | — | — | — |
| headroom_default | +22.0pp | +13.3pp | +6.7pp | +23.3pp | +36.7pp | +23.3pp | +20.9pp |
| summary_prompt | -2.0pp | +3.3pp | +0.0pp | +3.3pp | +13.3pp | +13.3pp | +5.2pp |

## Compression ratio (final / original tokens)

| arm | single-session-user | multi-session | temporal-reasoning | knowledge-update | single-session-assistant | single-session-preference | grand mean |
|---|---|---|---|---|---|---|---|
| baseline | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| headroom_default | 54.3% | 55.8% | 55.0% | 55.3% | 55.3% | 54.7% | 55.1% |
| summary_prompt | 39.5% | 39.6% | 39.5% | 39.5% | 39.3% | 39.4% | 39.5% |

## p50 latency (ms per case)

| arm | single-session-user | multi-session | temporal-reasoning | knowledge-update | single-session-assistant | single-session-preference | grand mean |
|---|---|---|---|---|---|---|---|
| baseline | 7100ms | 9680ms | 7924ms | 9696ms | 8965ms | 11926ms | 9215ms |
| headroom_default | 4375ms | 5927ms | 6424ms | 4131ms | 5101ms | 7561ms | 5586ms |
| summary_prompt | 8489ms | 9631ms | 8812ms | 8477ms | 9351ms | 11600ms | 9393ms |

## Sample sizes

| question type | source | n | n errors (baseline) |
|---|---|---|---|
| single-session-user | `n50/` | 50 | 0 |
| multi-session | `by_type/multi-session/` | 30 | 12 |
| temporal-reasoning | `by_type/temporal-reasoning_rerun/` | 30 | 0 |
| knowledge-update | `by_type/knowledge-update/` | 30 | 3 |
| single-session-assistant | `by_type/single-session-assistant/` | 30 | 7 |
| single-session-preference | `by_type/single-session-preference/` | 30 | 10 |

## Headline interpretation

Compare the **headroom_default** row of the Δ-quality table against zero:
- Positive values mean Headroom **outperforms** uncompressed baseline on that type.
- Negative values mean Headroom **loses** information critical for that question type.

The N=50 headline run on `single-session-user` showed +22pp.
This meta-report tells us whether that finding **generalizes** across question types,
which is the highest-priority Phase 2 question Karina and Sohrab asked us to answer.
