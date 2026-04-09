"""Statistical analysis helper for compaction-compare scored reports.

Reads any `scored_report.json` produced by the compaction-compare driver
and emits rigorous significance claims on top of the observed quality
rates and deltas:

  * **Clopper–Pearson 95% CIs** on each arm's quality correct rate.
    Exact binomial, no normal approximation — correct at all N, no
    weird edge cases at 0% or 100%.
  * **McNemar's test** for paired per-case comparisons between arms.
    The same 50 (or 30) cases are judged on every arm, so per-case
    quality-correct outcomes are paired, not independent. McNemar's
    is the textbook correct test for this design.
  * **Bootstrap 95% CI on the quality delta** (10 000 resamples).
    Robust to distributional assumptions, captures paired structure
    via joint resampling.
  * **Cohen's h** effect size for proportion differences. Gives a
    unit-free "how big is this" number to go alongside the p-value.

The output is a markdown table ready to paste into the report.

Usage:
    uv run python research/statistical_analysis.py <scored_report.json>
    uv run python research/statistical_analysis.py <dir>        # all scored reports under dir

Design notes:

- Only operates on `quality_correct` booleans (the `score >= 3` bar the
  judge uses). Rate-based analysis is the right fit for a 1–5 quality
  score; we intentionally don't report means on the 1–5 scale because
  the judge's scale isn't interval-valid.
- Deltas are always reported relative to a designated `baseline_arm`.
  By default this is whatever the scored report itself names
  (`data['baseline_arm']`), falling back to the literal string
  'baseline'. Pass `--baseline-arm <name>` to override.
- Cases with `error is not None` are excluded from every arm's N. This
  matches the driver's aggregate behaviour and keeps paired analysis
  honest — a case that errored on one arm isn't pairable.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scipy import stats


# ---------------------------------------------------------------------------
# Statistical primitives
# ---------------------------------------------------------------------------


def clopper_pearson_ci(
    n_correct: int, n_total: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Exact Clopper–Pearson binomial confidence interval.

    Returns (lower, upper) on the rate in [0, 1]. Handles n_correct=0
    and n_correct=n_total without the usual normal-approximation edge
    cases.
    """
    if n_total == 0:
        return (0.0, 0.0)
    alpha = 1.0 - confidence
    lower = (
        0.0 if n_correct == 0 else stats.beta.ppf(alpha / 2, n_correct, n_total - n_correct + 1)
    )
    upper = (
        1.0
        if n_correct == n_total
        else stats.beta.ppf(1 - alpha / 2, n_correct + 1, n_total - n_correct)
    )
    return (float(lower), float(upper))


def mcnemar_test(
    arm_a_correct: list[bool], arm_b_correct: list[bool]
) -> tuple[float, int, int]:
    """McNemar's test for paired binary outcomes.

    ``arm_a_correct`` and ``arm_b_correct`` must be aligned lists of the
    same length — one boolean per case, in the same case order, for each
    arm being compared.

    Returns (p_value, b, c) where:
      * ``b`` = number of cases where A wins and B loses (arm_a=True, arm_b=False)
      * ``c`` = number of cases where B wins and A loses (arm_a=False, arm_b=True)

    Uses the exact binomial test when b + c is small (<= 25) and the
    chi-square approximation otherwise. Scipy's ``stats.binomtest``
    provides the exact path.
    """
    if len(arm_a_correct) != len(arm_b_correct):
        raise ValueError(
            f"arm lists must be same length: {len(arm_a_correct)} vs {len(arm_b_correct)}"
        )
    b = sum(1 for a, bb in zip(arm_a_correct, arm_b_correct) if a and not bb)
    c = sum(1 for a, bb in zip(arm_a_correct, arm_b_correct) if not a and bb)

    n = b + c
    if n == 0:
        # No disagreement at all → p = 1
        return (1.0, b, c)
    if n <= 25:
        result = stats.binomtest(min(b, c), n=n, p=0.5, alternative="two-sided")
        return (float(result.pvalue), b, c)
    # Chi-square approximation for larger n (with continuity correction)
    chi2 = (abs(b - c) - 1) ** 2 / n
    p = 1.0 - stats.chi2.cdf(chi2, df=1)
    return (float(p), b, c)


def bootstrap_delta_ci(
    arm_a_correct: list[bool],
    arm_b_correct: list[bool],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 12345,
) -> tuple[float, float, float]:
    """Bootstrap 95% CI on the paired quality delta (rate_a − rate_b).

    Resamples case indices with replacement ``n_resamples`` times (both
    arms together to preserve pairing), computes the delta on each
    resample, and returns (point_estimate, lower, upper) on the delta
    in the [-1, 1] range.
    """
    if len(arm_a_correct) != len(arm_b_correct):
        raise ValueError("arm lists must be same length")
    n = len(arm_a_correct)
    if n == 0:
        return (0.0, 0.0, 0.0)

    import random

    rng = random.Random(seed)
    deltas: list[float] = []
    a_vals = [1 if x else 0 for x in arm_a_correct]
    b_vals = [1 if x else 0 for x in arm_b_correct]

    point = (sum(a_vals) - sum(b_vals)) / n

    for _ in range(n_resamples):
        indices = [rng.randrange(n) for _ in range(n)]
        a_sum = sum(a_vals[i] for i in indices)
        b_sum = sum(b_vals[i] for i in indices)
        deltas.append((a_sum - b_sum) / n)

    deltas.sort()
    alpha = 1.0 - confidence
    lo_idx = int(math.floor(alpha / 2 * n_resamples))
    hi_idx = int(math.ceil((1 - alpha / 2) * n_resamples)) - 1
    lo_idx = max(0, min(lo_idx, n_resamples - 1))
    hi_idx = max(0, min(hi_idx, n_resamples - 1))
    return (point, deltas[lo_idx], deltas[hi_idx])


def cohens_h(rate_a: float, rate_b: float) -> float:
    """Cohen's h effect size for two proportions.

    h = 2 · (arcsin(√rate_a) − arcsin(√rate_b))

    Conventions: |h| ≈ 0.2 is small, 0.5 is medium, 0.8 is large.
    Useful as a unit-free "how big is this delta" number to report
    alongside the p-value.
    """
    return 2.0 * (math.asin(math.sqrt(rate_a)) - math.asin(math.sqrt(rate_b)))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


@dataclass
class ArmStats:
    arm: str
    n: int
    n_correct: int
    rate: float
    ci_low: float
    ci_high: float


@dataclass
class PairwiseStats:
    arm_a: str
    arm_b: str
    delta: float
    delta_ci_low: float
    delta_ci_high: float
    mcnemar_p: float
    mcnemar_b: int  # A wins, B loses
    mcnemar_c: int  # B wins, A loses
    cohens_h: float


def _extract_arm_outcomes(scored_path: Path, baseline_arm_override: str | None = None):
    data = json.loads(scored_path.read_text())
    cases_by_arm = data.get("cases_by_arm") or {}
    baseline_arm = baseline_arm_override or data.get("baseline_arm") or "baseline"

    # Collect per-case correct-booleans, in case order, filtering out
    # cases where ANY arm errored (to preserve pairing).
    # First: figure out which case_ids are fully usable across all arms.
    arm_order = list(cases_by_arm.keys())
    if not arm_order:
        return None, None, None

    # Build case_id → per-arm outcome dict
    all_case_ids: set[str] = set()
    for arm, cases in cases_by_arm.items():
        for c in cases:
            all_case_ids.add(c["case_id"])

    # Index each arm by case_id for fast lookup
    arm_indexed: dict[str, dict[str, dict]] = {}
    for arm, cases in cases_by_arm.items():
        arm_indexed[arm] = {c["case_id"]: c for c in cases}

    # Keep only case_ids where every arm has a non-errored result
    usable_case_ids: list[str] = []
    for cid in sorted(all_case_ids):
        ok = True
        for arm in arm_order:
            case = arm_indexed[arm].get(cid)
            if case is None or case.get("error"):
                ok = False
                break
        if ok:
            usable_case_ids.append(cid)

    # Build the paired outcome table
    outcomes: dict[str, list[bool]] = {
        arm: [bool(arm_indexed[arm][cid].get("quality_correct")) for cid in usable_case_ids]
        for arm in arm_order
    }

    return arm_order, outcomes, baseline_arm


def analyse(scored_path: Path, baseline_arm_override: str | None = None) -> str:
    """Analyse a single scored_report.json and return a markdown report."""
    arm_order, outcomes, baseline_arm = _extract_arm_outcomes(
        scored_path, baseline_arm_override
    )
    if not arm_order or outcomes is None:
        return f"# {scored_path}\n\n(no arms found)\n"

    # Per-arm rate and CI
    arm_stats: list[ArmStats] = []
    for arm in arm_order:
        outs = outcomes[arm]
        n = len(outs)
        n_correct = sum(outs)
        rate = n_correct / n if n else 0.0
        ci_low, ci_high = clopper_pearson_ci(n_correct, n)
        arm_stats.append(
            ArmStats(
                arm=arm, n=n, n_correct=n_correct, rate=rate, ci_low=ci_low, ci_high=ci_high
            )
        )

    # Pairwise vs baseline
    if baseline_arm not in outcomes:
        baseline_arm = arm_order[0]
    baseline_outs = outcomes[baseline_arm]

    pair_stats: list[PairwiseStats] = []
    for arm in arm_order:
        if arm == baseline_arm:
            continue
        arm_outs = outcomes[arm]
        delta, lo, hi = bootstrap_delta_ci(arm_outs, baseline_outs)
        p, b, c = mcnemar_test(arm_outs, baseline_outs)
        a_rate = sum(arm_outs) / len(arm_outs)
        b_rate = sum(baseline_outs) / len(baseline_outs)
        h = cohens_h(a_rate, b_rate)
        pair_stats.append(
            PairwiseStats(
                arm_a=arm,
                arm_b=baseline_arm,
                delta=delta,
                delta_ci_low=lo,
                delta_ci_high=hi,
                mcnemar_p=p,
                mcnemar_b=b,
                mcnemar_c=c,
                cohens_h=h,
            )
        )

    # Render markdown
    lines: list[str] = []
    lines.append(f"## Statistical analysis — `{scored_path}`")
    lines.append("")
    lines.append(
        f"**Sample:** {arm_stats[0].n} cases paired across {len(arm_stats)} arms "
        f"(errored cases excluded from all arms to preserve pairing). "
        f"**Baseline arm:** `{baseline_arm}`."
    )
    lines.append("")
    lines.append("### Per-arm quality rate with 95% Clopper–Pearson CI")
    lines.append("")
    lines.append("| arm | n correct | n | rate | 95% CI |")
    lines.append("|---|---:|---:|---:|---|")
    for s in arm_stats:
        lines.append(
            f"| `{s.arm}` | {s.n_correct} | {s.n} | {s.rate * 100:.1f}% | "
            f"[{s.ci_low * 100:.1f}%, {s.ci_high * 100:.1f}%] |"
        )
    lines.append("")

    lines.append(f"### Pairwise vs `{baseline_arm}` — bootstrap CI + McNemar's paired test")
    lines.append("")
    lines.append(
        "| arm | Δ rate | 95% bootstrap CI on Δ | McNemar b / c | McNemar p | Cohen's h |"
    )
    lines.append("|---|---:|---|---:|---:|---:|")
    for p in pair_stats:
        delta_sign = "+" if p.delta >= 0 else ""
        p_str = f"{p.mcnemar_p:.4f}" if p.mcnemar_p >= 0.0001 else "< 0.0001"
        lines.append(
            f"| `{p.arm_a}` | **{delta_sign}{p.delta * 100:.1f} pp** | "
            f"[{p.delta_ci_low * 100:+.1f}pp, {p.delta_ci_high * 100:+.1f}pp] | "
            f"{p.mcnemar_b} / {p.mcnemar_c} | {p_str} | {p.cohens_h:+.2f} |"
        )
    lines.append("")
    lines.append("**Reading the columns**")
    lines.append("")
    lines.append(
        "- **Δ rate**: arm quality rate minus baseline quality rate, in percentage points."
    )
    lines.append(
        "- **Bootstrap CI on Δ**: 95% confidence interval on the paired delta, 10 000 "
        "resamples of the case set (preserves pairing). A CI that excludes 0 indicates "
        "a significant delta in the direction of the sign."
    )
    lines.append(
        "- **McNemar b / c**: cases where arm A wins and baseline loses (b) vs cases where "
        "baseline wins and arm A loses (c). Only the discordant pairs (b+c) count toward "
        "the test."
    )
    lines.append(
        "- **McNemar p**: two-sided p-value from the exact binomial form (for b+c ≤ 25) "
        "or the chi-square approximation with continuity correction (for b+c > 25)."
    )
    lines.append(
        "- **Cohen's h**: unit-free effect size for the rate difference. |h| ≈ 0.2 small, "
        "0.5 medium, 0.8 large. A positive sign means the arm beats baseline."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _find_scored_reports(root: Path) -> Iterable[Path]:
    if root.is_file() and root.name == "scored_report.json":
        yield root
        return
    for p in sorted(root.rglob("scored_report.json")):
        yield p


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Statistical analysis of compaction-compare scored reports"
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to a scored_report.json OR a directory containing scored_report.json files",
    )
    parser.add_argument(
        "--baseline-arm",
        type=str,
        default=None,
        help="Override the baseline arm for pairwise comparisons (default: from report)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write markdown output to this file instead of stdout",
    )
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(f"Path does not exist: {args.path}")

    md_chunks: list[str] = []
    for scored in _find_scored_reports(args.path):
        md = analyse(scored, baseline_arm_override=args.baseline_arm)
        md_chunks.append(md)

    if not md_chunks:
        raise SystemExit(f"No scored_report.json files found under {args.path}")

    full = "\n---\n\n".join(md_chunks) + "\n"
    if args.output:
        args.output.write_text(full)
        print(f"Wrote {args.output}")
    else:
        print(full)


if __name__ == "__main__":
    main()
