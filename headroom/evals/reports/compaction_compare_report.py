"""Quality scoring and Markdown/JSON renderers for CompactionCompareReport.

This module adds the report-card layer on top of the raw driver output produced
by CompactionCompareDriver.  It is intentionally decoupled from the existing
report_card.py (which serves SuiteResult).
"""

from __future__ import annotations

import dataclasses
import json
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from headroom.evals.core import EvalCase, EvalSuite
from headroom.evals.runners.compaction_compare import (
    CompactionCompareConfig,
    CompactionCompareReport,
)

# Type for a judge function: (question, ground_truth, prediction) -> (score, reasoning)
JudgeFn = Callable[[str, str, str], tuple[float, str]]


@dataclass
class ScoredCase:
    """One CompactionResult enriched with a quality score."""

    case_id: str
    arm: str
    answer: str
    ground_truth: str | None
    quality_score: float  # 1-5 from the judge, or 0.0 if no ground truth
    quality_correct: bool  # True if score >= 3
    quality_reasoning: str
    compression_ratio: float
    final_input_tokens: int
    original_input_tokens: int
    latency_ms: float
    n_iterations: int
    n_compactions: int
    error: str | None = None


@dataclass
class ArmAggregate:
    """Per-arm aggregated metrics."""

    arm: str
    n_cases: int
    n_errors: int
    # Quality
    mean_quality_score: float
    quality_correct_rate: float  # fraction with score >= 3
    delta_quality_correct_rate: float  # arm rate - baseline rate (signed)
    # Compression / cost
    mean_compression_ratio: float
    mean_original_tokens: float
    mean_final_tokens: float
    # Latency
    p50_latency_ms: float
    p95_latency_ms: float
    # Behavior
    mean_n_iterations: float
    mean_n_compactions: float
    # Per-question-type breakdown
    quality_correct_rate_by_qtype: dict[str, float] = field(default_factory=dict)


@dataclass
class CompactionCompareScored:
    """Full scored report — pairs raw driver output with quality scores + aggregates."""

    suite_name: str
    config: CompactionCompareConfig
    cases_by_arm: dict[str, list[ScoredCase]]
    aggregates: list[ArmAggregate]  # baseline first if present
    baseline_arm: str | None  # which arm was used as baseline for delta calc


def score_report(
    report: CompactionCompareReport,
    suite: EvalSuite,
    judge: JudgeFn,
    baseline_arm: str = "baseline",
) -> CompactionCompareScored:
    """Score every (arm, case) pair using the supplied judge and aggregate."""
    # Build case_id → EvalCase lookup
    case_lookup: dict[str, EvalCase] = {c.id: c for c in suite.cases}

    cases_by_arm: dict[str, list[ScoredCase]] = {}

    for arm, results in report.results.items():
        arm_cases: list[ScoredCase] = []
        for result in results:
            case = case_lookup.get(result.case_id)

            if result.error is not None:
                scored_case = ScoredCase(
                    case_id=result.case_id,
                    arm=arm,
                    answer=result.answer,
                    ground_truth=case.ground_truth if case else None,
                    quality_score=0.0,
                    quality_correct=False,
                    quality_reasoning=f"runner error: {result.error}",
                    compression_ratio=result.compression_ratio,
                    final_input_tokens=result.final_input_tokens,
                    original_input_tokens=result.original_input_tokens,
                    latency_ms=result.latency_ms,
                    n_iterations=result.n_iterations,
                    n_compactions=result.n_compactions,
                    error=result.error,
                )
            elif case is None or case.ground_truth is None:
                scored_case = ScoredCase(
                    case_id=result.case_id,
                    arm=arm,
                    answer=result.answer,
                    ground_truth=None,
                    quality_score=0.0,
                    quality_correct=False,
                    quality_reasoning="no ground_truth available",
                    compression_ratio=result.compression_ratio,
                    final_input_tokens=result.final_input_tokens,
                    original_input_tokens=result.original_input_tokens,
                    latency_ms=result.latency_ms,
                    n_iterations=result.n_iterations,
                    n_compactions=result.n_compactions,
                    error=None,
                )
            else:
                score, reasoning = judge(case.query, case.ground_truth, result.answer)
                scored_case = ScoredCase(
                    case_id=result.case_id,
                    arm=arm,
                    answer=result.answer,
                    ground_truth=case.ground_truth,
                    quality_score=score,
                    quality_correct=score >= 3.0,
                    quality_reasoning=reasoning,
                    compression_ratio=result.compression_ratio,
                    final_input_tokens=result.final_input_tokens,
                    original_input_tokens=result.original_input_tokens,
                    latency_ms=result.latency_ms,
                    n_iterations=result.n_iterations,
                    n_compactions=result.n_compactions,
                    error=None,
                )

            arm_cases.append(scored_case)

        cases_by_arm[arm] = arm_cases

    # Determine baseline correct rate for delta calculations
    actual_baseline_arm: str | None = baseline_arm if baseline_arm in cases_by_arm else None
    baseline_correct_rate: float = 0.0
    if actual_baseline_arm is not None:
        baseline_cases = cases_by_arm[actual_baseline_arm]
        if baseline_cases:
            baseline_correct_rate = sum(1 for sc in baseline_cases if sc.quality_correct) / len(
                baseline_cases
            )

    # Build aggregates
    aggregates: list[ArmAggregate] = []
    for arm, arm_cases in cases_by_arm.items():
        non_error = [sc for sc in arm_cases if sc.error is None]
        n_cases = len(arm_cases)
        n_errors = sum(1 for sc in arm_cases if sc.error is not None)

        mean_quality_score = (
            statistics.mean(sc.quality_score for sc in non_error) if non_error else 0.0
        )
        quality_correct_rate = (
            sum(1 for sc in arm_cases if sc.quality_correct) / n_cases if n_cases > 0 else 0.0
        )

        if actual_baseline_arm is not None and arm == actual_baseline_arm:
            delta = 0.0
        elif actual_baseline_arm is not None:
            delta = quality_correct_rate - baseline_correct_rate
        else:
            delta = 0.0

        mean_compression_ratio = (
            statistics.mean(sc.compression_ratio for sc in non_error) if non_error else 0.0
        )
        mean_original_tokens = (
            statistics.mean(sc.original_input_tokens for sc in non_error) if non_error else 0.0
        )
        mean_final_tokens = (
            statistics.mean(sc.final_input_tokens for sc in non_error) if non_error else 0.0
        )

        latencies = [sc.latency_ms for sc in non_error]
        if len(latencies) >= 2:
            p50 = statistics.median(latencies)
            sorted_lat = sorted(latencies)
            p95_idx = int(0.95 * len(sorted_lat))
            p95 = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]
        elif len(latencies) == 1:
            p50 = latencies[0]
            p95 = latencies[0]
        else:
            p50 = 0.0
            p95 = 0.0

        mean_n_iterations = (
            statistics.mean(sc.n_iterations for sc in non_error) if non_error else 0.0
        )
        mean_n_compactions = (
            statistics.mean(sc.n_compactions for sc in non_error) if non_error else 0.0
        )

        # Per-question-type breakdown (using the case lookup from suite)
        case_lookup: dict[str, EvalCase] = {c.id: c for c in suite.cases}
        qtype_buckets: dict[str, list[ScoredCase]] = {}
        for sc in arm_cases:
            ev = case_lookup.get(sc.case_id)
            qtype = ev.metadata.get("question_type", "unknown") if ev else "unknown"
            qtype_buckets.setdefault(qtype, []).append(sc)

        quality_correct_rate_by_qtype = {
            qtype: sum(1 for sc in bucket if sc.quality_correct) / len(bucket)
            for qtype, bucket in qtype_buckets.items()
            if bucket
        }

        aggregates.append(
            ArmAggregate(
                arm=arm,
                n_cases=n_cases,
                n_errors=n_errors,
                mean_quality_score=mean_quality_score,
                quality_correct_rate=quality_correct_rate,
                delta_quality_correct_rate=delta,
                mean_compression_ratio=mean_compression_ratio,
                mean_original_tokens=mean_original_tokens,
                mean_final_tokens=mean_final_tokens,
                p50_latency_ms=p50,
                p95_latency_ms=p95,
                mean_n_iterations=mean_n_iterations,
                mean_n_compactions=mean_n_compactions,
                quality_correct_rate_by_qtype=quality_correct_rate_by_qtype,
            )
        )

    # Order aggregates: baseline first, then rest in report.config.arms order
    def _sort_key(agg: ArmAggregate) -> tuple[int, int]:
        is_baseline = 0 if agg.arm == actual_baseline_arm else 1
        try:
            pos = report.config.arms.index(agg.arm)
        except ValueError:
            pos = 999
        return (is_baseline, pos)

    aggregates.sort(key=_sort_key)

    return CompactionCompareScored(
        suite_name=report.suite_name,
        config=report.config,
        cases_by_arm=cases_by_arm,
        aggregates=aggregates,
        baseline_arm=actual_baseline_arm,
    )


def render_markdown(scored: CompactionCompareScored) -> str:
    """Render the headline Markdown report."""
    lines: list[str] = []

    lines.append(f"# Compaction Compare — {scored.suite_name}")
    lines.append("")

    # Config block
    lines.append("## Configuration")
    lines.append("")
    lines.append(f"- **Provider**: {scored.config.provider}")
    lines.append(f"- **Model**: {scored.config.model}")
    lines.append(f"- **Threshold**: {scored.config.threshold:,} tokens")
    lines.append(f"- **Arms**: {', '.join(scored.config.arms)}")
    lines.append(f"- **Baseline arm**: {scored.baseline_arm or 'none'}")
    lines.append("")

    # Headline table
    lines.append("## Results")
    lines.append("")
    header = (
        "| arm | n | compression | delta quality vs baseline"
        " | quality correct | p50 latency | mean compactions | errors |"
    )
    sep = "|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)

    for agg in scored.aggregates:
        delta = agg.delta_quality_correct_rate
        if abs(delta) < 1e-9:
            delta_str = "+0.0%"
        elif delta > 0:
            delta_str = f"+{delta:.1%}"
        else:
            delta_str = f"-{abs(delta):.1%}"

        lines.append(
            f"| {agg.arm}"
            f" | {agg.n_cases}"
            f" | {agg.mean_compression_ratio:.1%}"
            f" | {delta_str}"
            f" | {agg.quality_correct_rate:.1%}"
            f" | {agg.p50_latency_ms:.0f}ms"
            f" | {agg.mean_n_compactions:.1f}"
            f" | {agg.n_errors}"
            f" |"
        )

    lines.append("")

    # Per-question-type breakdown
    all_qtypes: list[str] = []
    for agg in scored.aggregates:
        for qt in agg.quality_correct_rate_by_qtype:
            if qt not in all_qtypes:
                all_qtypes.append(qt)

    if all_qtypes:
        lines.append("## Per Question Type Breakdown")
        lines.append("")
        qt_header = "| arm | " + " | ".join(all_qtypes) + " |"
        qt_sep = "|---|" + "|".join(["---"] * len(all_qtypes)) + "|"
        lines.append(qt_header)
        lines.append(qt_sep)
        for agg in scored.aggregates:
            row_cells = []
            for qt in all_qtypes:
                rate = agg.quality_correct_rate_by_qtype.get(qt)
                if rate is None:
                    row_cells.append("n/a")
                else:
                    row_cells.append(f"{rate:.1%}")
            lines.append(f"| {agg.arm} | " + " | ".join(row_cells) + " |")
        lines.append("")

    # Threshold sweep placeholder
    lines.append("## Threshold Sweep")
    lines.append("")
    lines.append(
        f"Single threshold run at {scored.config.threshold:,} tokens. "
        "Multi-threshold sweeps can be merged here by a future caller."
    )
    lines.append("")

    # Notes
    lines.append("## Notes")
    lines.append("")
    lines.append(f"- Answer model: `{scored.config.model}`")
    lines.append(f"- Summary model: `{scored.config.summary_model}`")

    # Errors summary
    error_cases = [
        (arm, sc) for arm, cases in scored.cases_by_arm.items() for sc in cases if sc.error
    ]
    if error_cases:
        lines.append("")
        lines.append("### Errors")
        lines.append("")
        for arm, sc in error_cases:
            lines.append(f"- `{arm}/{sc.case_id}`: {sc.error}")

    lines.append("")

    return "\n".join(lines)


def render_json(scored: CompactionCompareScored) -> str:
    """Render the full scored report as JSON."""
    return json.dumps(dataclasses.asdict(scored), indent=2, default=str)


def save_reports(
    scored: CompactionCompareScored,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write report.md, scored_report.json, and summary.txt.

    Returns a dict mapping format name -> path written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md_path = out / "report.md"
    md_path.write_text(render_markdown(scored))

    json_path = out / "scored_report.json"
    json_path.write_text(render_json(scored))

    # summary.txt — one line per arm
    summary_lines: list[str] = []
    total = sum(agg.n_cases for agg in scored.aggregates)
    for agg in scored.aggregates:
        line = (
            f"{agg.arm}: n={agg.n_cases}/{total}"
            f" | quality={agg.quality_correct_rate:.1%}"
            f" | delta={agg.delta_quality_correct_rate:+.1%}"
            f" | compression={agg.mean_compression_ratio:.1%}"
            f" | latency_p50={agg.p50_latency_ms:.0f}ms"
        )
        summary_lines.append(line)

    summary_path = out / "summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n")

    return {
        "markdown": md_path,
        "json": json_path,
        "summary": summary_path,
    }
