"""Retrofit cost_usd onto the existing OpenAI-side scored report.

When the 2026-04-09 cross-provider N=50 sweep ran, _call_openai in
direct_runners.py returned cost_usd=0.0 as a placeholder because the
pricing table in providers/anthropic.py only covered Claude models. The
runs themselves are valid — we captured final_input_tokens for every
case — but cost_usd on every OpenAI case is currently 0.0.

This script recomputes cost_usd for every case in the existing
scored_report.json by:

  1. Looking up the model's input/output token prices via litellm.model_cost.
  2. For each case:
       - input_cost  = final_input_tokens × input_rate
       - output_cost = tiktoken(answer)    × output_rate
       - cost_usd    = input_cost + output_cost
  3. Recomputing total_cost_usd and mean_cost_per_case_usd on each arm's
     aggregate.
  4. Writing the updated scored_report.json back in place, and
     regenerating report.md / summary.txt via the existing report
     renderer so all three artifacts stay in sync.

Notes and caveats:

- final_input_tokens is the billable input count for ALL three OpenAI arms
  in this sweep, including openai_compact_v2. The runner populates it
  from usage.input_tokens post-compaction, which matches what OpenAI
  actually billed. That's the number we want to multiply by the input
  rate.
- Output tokens are estimated via tiktoken(cl100k_base) on the answer
  text. This is slightly inaccurate vs OpenAI's own tokenizer but is
  within a few percent for English text — accurate enough for cost
  estimates meant for business-case framing.
- The cache_read_input_token_cost from litellm is NOT applied here
  because none of the arms in this sweep used prompt caching. If a
  future run uses caching, this retrofit would need to know the split.

Usage:
    uv run python research/retrofit_openai_costs.py <scored_report.json>

If no path is given, defaults to the 2026-04-09 cross-provider OpenAI run.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

DEFAULT_SCORED_PATH = Path(
    "eval_results/compaction_compare/longmemeval/openai_gpt54/n50_3arm/scored_report.json"
)


def get_pricing(model: str) -> tuple[float, float]:
    """Return (input_price_per_token, output_price_per_token) via litellm.model_cost.

    Raises RuntimeError with a clear message if the model is unknown.
    """
    import litellm

    cost = getattr(litellm, "model_cost", {}) or {}
    if model not in cost:
        raise RuntimeError(
            f"Model {model!r} not in litellm.model_cost. "
            f"Check the model id or update litellm."
        )
    entry = cost[model]
    in_rate = entry.get("input_cost_per_token")
    out_rate = entry.get("output_cost_per_token")
    if in_rate is None or out_rate is None:
        raise RuntimeError(
            f"Model {model!r} is in litellm.model_cost but missing pricing "
            f"(in={in_rate}, out={out_rate}). Needs a manual override."
        )
    return float(in_rate), float(out_rate)


def count_tokens(text: str) -> int:
    """Count tokens with tiktoken cl100k_base (reasonable English approximation)."""
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text or ""))


def retrofit(scored_path: Path) -> None:
    with scored_path.open() as f:
        data = json.load(f)

    cfg = data.get("config") or {}
    model = cfg.get("model")
    if not model:
        raise RuntimeError(f"No config.model in {scored_path}")

    in_rate, out_rate = get_pricing(model)
    print(f"Model: {model}")
    print(f"  input:  ${in_rate * 1_000_000:.2f}/M tokens")
    print(f"  output: ${out_rate * 1_000_000:.2f}/M tokens")
    print()

    cases_by_arm = data.get("cases_by_arm") or {}
    n_cases_total = 0

    for arm_name, cases in cases_by_arm.items():
        if not cases:
            continue
        arm_total = 0.0
        arm_n_ok = 0
        for case in cases:
            if case.get("error"):
                # Keep cost_usd at 0 for errored cases — no API charge incurred.
                case["cost_usd"] = 0.0
                continue
            fin_in = case.get("final_input_tokens") or 0
            answer = case.get("answer") or ""
            out_toks = count_tokens(answer)
            cost = fin_in * in_rate + out_toks * out_rate
            case["cost_usd"] = cost
            arm_total += cost
            arm_n_ok += 1
        arm_mean = (arm_total / arm_n_ok) if arm_n_ok else 0.0
        n_cases_total += len(cases)
        print(
            f"  {arm_name}: n_ok={arm_n_ok} "
            f"total=${arm_total:.4f} mean/case=${arm_mean:.4f}"
        )

    # Recompute per-arm aggregates for total_cost_usd / mean_cost_per_case_usd.
    for agg in data.get("aggregates") or []:
        arm = agg.get("arm")
        cases = cases_by_arm.get(arm) or []
        non_error = [c for c in cases if not c.get("error")]
        costs = [c.get("cost_usd", 0.0) for c in non_error]
        total = sum(costs)
        mean = (total / len(costs)) if costs else 0.0
        agg["total_cost_usd"] = total
        agg["mean_cost_per_case_usd"] = mean

    # Write back scored_report.json.
    scored_path.write_text(json.dumps(data, indent=2, default=str))
    print(f"\nWrote {scored_path}")

    # Regenerate report.md and summary.txt via the existing renderer.
    _rerender(data, scored_path.parent)


def _rerender(scored_dict: dict, out_dir: Path) -> None:
    """Use render_markdown / save_reports on a reconstructed CompactionCompareScored."""
    from headroom.evals.reports.compaction_compare_report import (
        ArmAggregate,
        CompactionCompareScored,
        ScoredCase,
        render_markdown,
    )
    from headroom.evals.runners.compaction_compare import CompactionCompareConfig

    # Reconstruct dataclasses from the dict (dataclasses.asdict is reversible by hand).
    cfg_dict = scored_dict.get("config") or {}
    # CompactionCompareConfig accepts all known fields; ignore unknown ones for forward compat.
    cfg_fields = {f.name for f in dataclasses.fields(CompactionCompareConfig)}
    config = CompactionCompareConfig(**{k: v for k, v in cfg_dict.items() if k in cfg_fields})

    cases_by_arm_raw = scored_dict.get("cases_by_arm") or {}
    sc_fields = {f.name for f in dataclasses.fields(ScoredCase)}
    cases_by_arm = {
        arm: [
            ScoredCase(**{k: v for k, v in c.items() if k in sc_fields}) for c in cases
        ]
        for arm, cases in cases_by_arm_raw.items()
    }

    agg_fields = {f.name for f in dataclasses.fields(ArmAggregate)}
    aggregates = [
        ArmAggregate(**{k: v for k, v in a.items() if k in agg_fields})
        for a in scored_dict.get("aggregates") or []
    ]

    scored = CompactionCompareScored(
        suite_name=scored_dict.get("suite_name", ""),
        config=config,
        cases_by_arm=cases_by_arm,
        aggregates=aggregates,
        baseline_arm=scored_dict.get("baseline_arm"),
    )

    md = render_markdown(scored)
    (out_dir / "report.md").write_text(md)
    print(f"Wrote {out_dir / 'report.md'}")

    # Regenerate summary.txt to match the updated aggregates
    summary_lines: list[str] = []
    total = sum(agg.n_cases for agg in scored.aggregates)
    for agg in scored.aggregates:
        line = (
            f"{agg.arm}: n={agg.n_cases}/{total}"
            f" | quality={agg.quality_correct_rate:.1%}"
            f" | delta={agg.delta_quality_correct_rate:+.1%}"
            f" | compression={agg.mean_compression_ratio:.1%}"
            f" | latency_p50={agg.p50_latency_ms:.0f}ms"
            f" | user_visible_p50={agg.p50_user_visible_latency_ms:.0f}ms"
            f" | mean_cost=${agg.mean_cost_per_case_usd:.4f}"
        )
        summary_lines.append(line)
    (out_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n")
    print(f"Wrote {out_dir / 'summary.txt'}")


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = DEFAULT_SCORED_PATH
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        sys.exit(1)
    retrofit(path)


if __name__ == "__main__":
    main()
