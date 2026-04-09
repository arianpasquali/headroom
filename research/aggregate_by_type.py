"""Aggregate per-question-type compaction-compare results into one cross-type report.

Reads `scored_report.json` from each `eval_results/compaction_compare/longmemeval/anthropic/by_type/<type>/`
directory plus the original `n50/` headline run, and produces a Markdown table
showing per-arm quality / compression / latency across all 6 LongMemEval
question types. Designed to be run by hand from the worktree root after the
Phase 2 sweeps complete.

Usage:
    uv run python research/aggregate_by_type.py

Writes:
    eval_results/compaction_compare/longmemeval/anthropic/cross_type_report.md
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path("eval_results/compaction_compare/longmemeval/anthropic")
BY_TYPE = ROOT / "by_type"
HEADLINE = ROOT / "n50"
OUT = ROOT / "cross_type_report.md"

# Question types in display order. The original headline run covers
# single-session-user; the by_type sweeps cover the other 5.
QUESTION_TYPES = [
    "single-session-user",  # from n50/
    "multi-session",
    "temporal-reasoning",
    "knowledge-update",
    "single-session-assistant",
    "single-session-preference",
]


def load_scored(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def aggregates_by_arm(scored: dict) -> dict[str, dict]:
    return {agg["arm"]: agg for agg in scored.get("aggregates", [])}


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.1f}%"


def fmt_delta(x: float | None) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x * 100:.1f}pp"


def fmt_ms(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:.0f}ms"


def main() -> None:
    # Map question_type → scored report
    reports: dict[str, dict] = {}

    # Headline run (single-session-user)
    headline = load_scored(HEADLINE / "scored_report.json")
    if headline is not None:
        reports["single-session-user"] = headline

    # Per-type sweeps
    for qtype in QUESTION_TYPES[1:]:
        scored = load_scored(BY_TYPE / qtype / "scored_report.json")
        if scored is not None:
            reports[qtype] = scored

    if not reports:
        print("No reports found. Did the Phase 2 sweeps complete?")
        return

    # Discover arms (use the first available report's order)
    first = next(iter(reports.values()))
    arms = [agg["arm"] for agg in first.get("aggregates", [])]

    lines: list[str] = []
    lines.append("# Compaction Compare — LongMemEval cross-type meta-report")
    lines.append("")
    lines.append("Aggregates the headline N=50 single-session-user run with the Phase 2")
    lines.append("N=30 sweeps across the other 5 LongMemEval question types. Built by")
    lines.append("`research/aggregate_by_type.py` from the per-type `scored_report.json` files.")
    lines.append("")
    lines.append("## Quality (correct rate per question type)")
    lines.append("")

    # Table: rows = arms, columns = question types + grand mean
    header = "| arm | " + " | ".join(reports.keys()) + " | grand mean |"
    sep = "|---|" + "|".join(["---"] * len(reports)) + "|---|"
    lines.append(header)
    lines.append(sep)

    grand_means_by_arm: dict[str, float] = {}
    for arm in arms:
        cells: list[str] = [arm]
        per_type_rates: list[float] = []
        for qtype, scored in reports.items():
            agg = aggregates_by_arm(scored).get(arm)
            if agg is None:
                cells.append("—")
                continue
            rate = agg["quality_correct_rate"]
            per_type_rates.append(rate)
            cells.append(fmt_pct(rate))
        grand = statistics.mean(per_type_rates) if per_type_rates else 0.0
        grand_means_by_arm[arm] = grand
        cells.append(fmt_pct(grand))
        lines.append("| " + " | ".join(cells) + " |")

    # Δ vs baseline row (per type)
    lines.append("")
    lines.append("## Δ quality vs baseline (per question type)")
    lines.append("")
    lines.append(header)
    lines.append(sep)
    baseline_per_type: dict[str, float] = {}
    for qtype, scored in reports.items():
        b = aggregates_by_arm(scored).get("baseline")
        if b is not None:
            baseline_per_type[qtype] = b["quality_correct_rate"]
    for arm in arms:
        if arm == "baseline":
            cells = ["baseline (reference)"]
            for _ in reports:
                cells.append("—")
            cells.append("—")
            lines.append("| " + " | ".join(cells) + " |")
            continue
        cells = [arm]
        deltas: list[float] = []
        for qtype, scored in reports.items():
            agg = aggregates_by_arm(scored).get(arm)
            base = baseline_per_type.get(qtype)
            if agg is None or base is None:
                cells.append("—")
                continue
            delta = agg["quality_correct_rate"] - base
            deltas.append(delta)
            cells.append(fmt_delta(delta))
        grand_delta = statistics.mean(deltas) if deltas else 0.0
        cells.append(fmt_delta(grand_delta))
        lines.append("| " + " | ".join(cells) + " |")

    # Compression ratio per arm × type
    lines.append("")
    lines.append("## Compression ratio (final / original tokens)")
    lines.append("")
    lines.append(header)
    lines.append(sep)
    for arm in arms:
        cells = [arm]
        ratios: list[float] = []
        for qtype, scored in reports.items():
            agg = aggregates_by_arm(scored).get(arm)
            if agg is None:
                cells.append("—")
                continue
            r = agg["mean_compression_ratio"]
            ratios.append(r)
            cells.append(fmt_pct(r))
        grand = statistics.mean(ratios) if ratios else 0.0
        cells.append(fmt_pct(grand))
        lines.append("| " + " | ".join(cells) + " |")

    # p50 latency
    lines.append("")
    lines.append("## p50 latency (ms per case)")
    lines.append("")
    lines.append(header)
    lines.append(sep)
    for arm in arms:
        cells = [arm]
        lats: list[float] = []
        for qtype, scored in reports.items():
            agg = aggregates_by_arm(scored).get(arm)
            if agg is None:
                cells.append("—")
                continue
            lat = agg["p50_latency_ms"]
            lats.append(lat)
            cells.append(fmt_ms(lat))
        grand = statistics.mean(lats) if lats else 0.0
        cells.append(fmt_ms(grand))
        lines.append("| " + " | ".join(cells) + " |")

    # Sample sizes
    lines.append("")
    lines.append("## Sample sizes")
    lines.append("")
    lines.append("| question type | n | n errors |")
    lines.append("|---|---|---|")
    for qtype, scored in reports.items():
        b = aggregates_by_arm(scored).get("baseline")
        n = b["n_cases"] if b else 0
        err = b["n_errors"] if b else 0
        lines.append(f"| {qtype} | {n} | {err} |")

    # Headline interpretation block
    lines.append("")
    lines.append("## Headline interpretation")
    lines.append("")
    lines.append("Compare the **headroom_default** row of the Δ-quality table against zero:")
    lines.append("- Positive values mean Headroom **outperforms** uncompressed baseline on that type.")
    lines.append("- Negative values mean Headroom **loses** information critical for that question type.")
    lines.append("")
    lines.append("The N=50 headline run on `single-session-user` showed +22pp.")
    lines.append("This meta-report tells us whether that finding **generalizes** across question types,")
    lines.append("which is the highest-priority Phase 2 question Karina and Sohrab asked us to answer.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
