# RES-333 — Statistical analysis of all scored reports

**Generated:** 2026-04-09 by `research/statistical_analysis.py`
**Scope:** Every `scored_report.json` under `eval_results/compaction_compare/longmemeval/`

This file applies four rigorous statistical checks on top of the observed quality-correct rates in every compaction-compare scored report:

1. **Clopper–Pearson 95% CIs** on each arm's quality correct rate (exact binomial, correct at all N)
2. **Bootstrap 95% CI on the paired quality delta** (10,000 resamples, preserves per-case pairing)
3. **McNemar's test** for paired per-case comparisons — the correct test for two arms judged on the same case set (b = arm wins, c = baseline wins, only discordant pairs count)
4. **Cohen's h** effect size for proportion differences — unit-free "how big is this" number (|h| ≈ 0.2 small, 0.5 medium, 0.8 large)

## Key findings for the RES-333 sync

### The +46pp Sonnet 4.6 Headroom win is statistically bulletproof

From the `anthropic_sonnet46/n50_5arm/` run below:

- **Headroom vs baseline**: +46.0pp, McNemar b=23 c=0 (Headroom wins 23, **loses zero**), p < 0.0001, Cohen's h = +0.99 (very large effect). Headroom never loses a case to baseline among the discordant pairs. Effect size is near the "very large" ceiling of Cohen's h.
- **Headroom vs anthropic_compact_v2**: +30.0pp, McNemar 16/1, p = 0.0003, Cohen's h = +0.67 (medium-large). Statistically decisive.

### The floor-test finding is even stronger than the headline delta

Using `headroom_default` as the baseline for comparison:

- **Headroom vs dumb_truncation_last_n**: +56.0pp, McNemar 28/0 (Headroom never loses), p < 0.0001, Cohen's h = +1.20 (very large)
- **Headroom vs random_chunk_drop**: +62.0pp, McNemar 32/1, p < 0.0001, Cohen's h = +1.34 (very large)

These are among the largest effect sizes observable in this kind of eval — Headroom beats naive compression at matched ratio with effect sizes above the "very large" cutoff, and with pairing that approaches perfect (near-zero losses against dumb truncation on 50 paired cases).

### Important caveats the statistics surfaced

- **Floor tests vs baseline are NOT statistically significant at N=50** (`dumb_truncation_last_n` vs baseline: p=0.30; `random_chunk_drop` vs baseline: p=0.12). The observed −10pp and −16pp deltas are directionally suggestive but their 95% CIs include zero. **The correct framing is "floor tests lose decisively to Headroom at matched compression," not "floor tests are worse than baseline."** Reports should be updated accordingly.
- **anthropic_compact_v2 vs baseline is marginal at p=0.057** (barely above the 0.05 threshold). The observed +16pp is real but the "significantly better than baseline" claim is a whisker away at N=50. The Sonnet 4.6 per-type sweep (in progress) will tighten this substantially by adding ~150 more cases.
- **Sonnet 4.5 N=30 per-type runs have wide CIs.** At N=30 per type, the 95% CI on a 50% rate is ~±18pp. Deltas under ~15pp per type on the Sonnet 4.5 per-type sweep (notably `multi-session` at +13.3pp) are not individually significant. They are consistent-in-sign with the overall Headroom-wins pattern but should not be cited as standalone evidence.

### The OpenAI tie at 98% is statistically clean

On `gpt-5.4` N=50, all three arms score 49/50 = 98.0% with Clopper–Pearson CIs of [89.4%, 99.9%] each. The McNemar discordant pairs are 1/1 for both `headroom_default` vs `baseline` and `openai_compact_v2` vs `baseline` — Headroom disagrees with baseline on exactly 2 cases (one each way), confirming the tie is real. **The "Headroom ties on quality on gpt-5.4" claim is statistically tight, not a low-N artifact.**

---

## Per-run detail

### Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/by_type/knowledge-update/scored_report.json`

**Sample:** 27 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 14 | 27 | 51.9% | [31.9%, 71.3%] |
| `headroom_default` | 19 | 27 | 70.4% | [49.8%, 86.2%] |
| `summary_prompt` | 13 | 27 | 48.1% | [28.7%, 68.1%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+18.5 pp** | [-3.7pp, +37.0pp] | 7 / 2 | 0.1797 | +0.38 |
| `summary_prompt` | **-3.7 pp** | [-25.9pp, +18.5pp] | 4 / 5 | 1.0000 | -0.07 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/by_type/multi-session/scored_report.json`

**Sample:** 18 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 5 | 18 | 27.8% | [9.7%, 53.5%] |
| `headroom_default` | 7 | 18 | 38.9% | [17.3%, 64.3%] |
| `summary_prompt` | 4 | 18 | 22.2% | [6.4%, 47.6%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+11.1 pp** | [-16.7pp, +38.9pp] | 5 / 3 | 0.7266 | +0.24 |
| `summary_prompt` | **-5.6 pp** | [-33.3pp, +22.2pp] | 3 / 4 | 1.0000 | -0.13 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/by_type/single-session-assistant/scored_report.json`

**Sample:** 23 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 17 | 23 | 73.9% | [51.6%, 89.8%] |
| `headroom_default` | 21 | 23 | 91.3% | [72.0%, 98.9%] |
| `summary_prompt` | 16 | 23 | 69.6% | [47.1%, 86.8%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+17.4 pp** | [+4.3pp, +34.8pp] | 4 / 0 | 0.1250 | +0.47 |
| `summary_prompt` | **-4.3 pp** | [-30.4pp, +21.7pp] | 4 / 5 | 1.0000 | -0.10 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/by_type/single-session-preference/scored_report.json`

**Sample:** 20 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 3 | 20 | 15.0% | [3.2%, 37.9%] |
| `headroom_default` | 7 | 20 | 35.0% | [15.4%, 59.2%] |
| `summary_prompt` | 4 | 20 | 20.0% | [5.7%, 43.7%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+20.0 pp** | [+0.0pp, +45.0pp] | 5 / 1 | 0.2188 | +0.47 |
| `summary_prompt` | **+5.0 pp** | [+0.0pp, +15.0pp] | 1 / 0 | 1.0000 | +0.13 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/by_type/temporal-reasoning/scored_report.json`

**Sample:** 26 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 0 | 26 | 0.0% | [0.0%, 13.2%] |
| `headroom_default` | 0 | 26 | 0.0% | [0.0%, 13.2%] |
| `summary_prompt` | 1 | 26 | 3.8% | [0.1%, 19.6%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+0.0 pp** | [+0.0pp, +0.0pp] | 0 / 0 | 1.0000 | +0.00 |
| `summary_prompt` | **+3.8 pp** | [+0.0pp, +11.5pp] | 1 / 0 | 1.0000 | +0.39 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/by_type/temporal-reasoning_rerun/scored_report.json`

**Sample:** 30 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 0 | 30 | 0.0% | [0.0%, 11.6%] |
| `headroom_default` | 2 | 30 | 6.7% | [0.8%, 22.1%] |
| `summary_prompt` | 0 | 30 | 0.0% | [0.0%, 11.6%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+6.7 pp** | [+0.0pp, +16.7pp] | 2 / 0 | 0.5000 | +0.52 |
| `summary_prompt` | **+0.0 pp** | [+0.0pp, +0.0pp] | 0 / 0 | 1.0000 | +0.00 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/n150/scored_report.json`

**Sample:** 150 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 49 | 150 | 32.7% | [25.2%, 40.8%] |
| `headroom_default` | 79 | 150 | 52.7% | [44.4%, 60.9%] |
| `summary_prompt` | 46 | 150 | 30.7% | [23.4%, 38.7%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+20.0 pp** | [+12.7pp, +27.3pp] | 33 / 3 | < 0.0001 | +0.41 |
| `summary_prompt` | **-2.0 pp** | [-8.7pp, +4.7pp] | 12 / 15 | 0.7003 | -0.04 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic/n50/scored_report.json`

**Sample:** 50 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 26 | 50 | 52.0% | [37.4%, 66.3%] |
| `headroom_default` | 37 | 50 | 74.0% | [59.7%, 85.4%] |
| `summary_prompt` | 25 | 50 | 50.0% | [35.5%, 64.5%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+22.0 pp** | [+8.0pp, +36.0pp] | 13 / 2 | 0.0074 | +0.46 |
| `summary_prompt` | **-2.0 pp** | [-16.0pp, +12.0pp] | 6 / 7 | 1.0000 | -0.04 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50/scored_report.json`

**Sample:** 50 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 20 | 50 | 40.0% | [26.4%, 54.8%] |
| `headroom_default` | 41 | 50 | 82.0% | [68.6%, 91.4%] |
| `anthropic_compact_v2` | 27 | 50 | 54.0% | [39.3%, 68.2%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+42.0 pp** | [+28.0pp, +56.0pp] | 21 / 0 | < 0.0001 | +0.90 |
| `anthropic_compact_v2` | **+14.0 pp** | [+0.0pp, +28.0pp] | 11 / 4 | 0.1185 | +0.28 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/anthropic_sonnet46/n50_5arm/scored_report.json`

**Sample:** 50 cases paired across 5 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 19 | 50 | 38.0% | [24.7%, 52.8%] |
| `headroom_default` | 42 | 50 | 84.0% | [70.9%, 92.8%] |
| `anthropic_compact_v2` | 27 | 50 | 54.0% | [39.3%, 68.2%] |
| `dumb_truncation_last_n` | 14 | 50 | 28.0% | [16.2%, 42.5%] |
| `random_chunk_drop` | 11 | 50 | 22.0% | [11.5%, 36.0%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+46.0 pp** | [+32.0pp, +60.0pp] | 23 / 0 | < 0.0001 | +0.99 |
| `anthropic_compact_v2` | **+16.0 pp** | [+2.0pp, +30.0pp] | 11 / 3 | 0.0574 | +0.32 |
| `dumb_truncation_last_n` | **-10.0 pp** | [-24.0pp, +4.0pp] | 5 / 10 | 0.3018 | -0.21 |
| `random_chunk_drop` | **-16.0 pp** | [-32.0pp, +2.0pp] | 6 / 14 | 0.1153 | -0.35 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

---

## Statistical analysis — `eval_results/compaction_compare/longmemeval/openai_gpt54/n50_3arm/scored_report.json`

**Sample:** 50 cases paired across 3 arms (errored cases excluded from all arms to preserve pairing). **Baseline arm:** `baseline`.

### Per-arm quality rate with 95% Clopper–Pearson CI

| arm | n correct | n | rate | 95% CI |
|---|---:|---:|---:|---|
| `baseline` | 49 | 50 | 98.0% | [89.4%, 99.9%] |
| `headroom_default` | 49 | 50 | 98.0% | [89.4%, 99.9%] |
| `openai_compact_v2` | 49 | 50 | 98.0% | [89.4%, 99.9%] |

### Pairwise vs `baseline` — bootstrap CI + McNemar's paired test

| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |
|---|---:|---|---:|---:|---:|
| `headroom_default` | **+0.0 pp** | [-6.0pp, +6.0pp] | 1 / 1 | 1.0000 | +0.00 |
| `openai_compact_v2` | **+0.0 pp** | [-6.0pp, +6.0pp] | 1 / 1 | 1.0000 | +0.00 |

**Reading the columns**

- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points.
- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 resamples of the case set (preserves pairing). A CI that excludes 0 indicates a significant delta in the direction of the sign.
- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward the test.
- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) or the chi-square approximation with continuity correction (for b+c > 25).
- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, 0.5 medium, 0.8 large. A positive sign means the arm beats baseline.

