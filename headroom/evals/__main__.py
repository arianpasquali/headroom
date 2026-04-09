"""CLI entry point for Headroom evaluation framework.

Usage:
    python -m headroom.evals quick              # Quick sanity check (5 samples)
    python -m headroom.evals benchmark          # Full benchmark suite
    python -m headroom.evals list               # List available datasets
    python -m headroom.evals --help             # Show help

Install dependencies:
    pip install headroom-ai[evals]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from headroom.evals.memory.judge import create_anthropic_judge

if TYPE_CHECKING:
    from headroom.evals.core import EvalResult


def cmd_quick(args: argparse.Namespace) -> None:
    """Run quick sanity check."""
    from headroom.evals.runners.before_after import run_quick_eval

    results = run_quick_eval(
        n_samples=args.n,
        provider=args.provider,
        model=args.model,
    )

    if args.output:
        results.save(args.output)
        print(f"\nResults saved to: {args.output}")

    # Exit with error if accuracy not preserved
    if results.accuracy_preservation_rate < 0.9:
        print("\nWARNING: Accuracy preservation rate below 90%!")
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    """List available datasets."""
    from headroom.evals.datasets import DATASET_REGISTRY, list_available_datasets

    print("\n" + "=" * 60)
    print("AVAILABLE EVALUATION DATASETS")
    print("=" * 60)

    by_category = list_available_datasets()

    for category, datasets in sorted(by_category.items()):
        category_title = category.replace("_", " ").title()
        print(f"\n{category_title}:")
        print("-" * 40)
        for name in sorted(datasets):
            info = DATASET_REGISTRY[name]
            default_n = info.get("default_n", "N/A")
            print(f"  {name:20} (n={default_n})")
            print(f"    {info['description']}")

    print("\n" + "=" * 60)
    print("Usage: python -m headroom.evals benchmark --dataset <name> -n <samples>")
    print("=" * 60 + "\n")


def cmd_benchmark(args: argparse.Namespace) -> None:
    """Run full benchmark suite."""
    from headroom.evals.datasets import (
        DATASET_REGISTRY,
        load_dataset_by_name,
        load_tool_output_samples,
    )
    from headroom.evals.runners.before_after import BeforeAfterRunner, LLMConfig

    print("=" * 60)
    print("HEADROOM COMPRESSION ACCURACY BENCHMARK")
    print("=" * 60)

    runner = BeforeAfterRunner(
        llm_config=LLMConfig(provider=args.provider, model=args.model),
        use_semantic_similarity=args.semantic,
    )

    all_results = []

    # Determine which datasets to run
    if args.dataset == "all":
        # Run all datasets
        dataset_names = list(DATASET_REGISTRY.keys())
    elif args.dataset == "quick":
        # Quick subset: tool_outputs + a few samples from each category
        dataset_names = ["tool_outputs", "squad", "bfcl"]
    elif args.dataset in DATASET_REGISTRY:
        dataset_names = [args.dataset]
    else:
        # Check if it's a category
        from headroom.evals.datasets import list_available_datasets

        by_category = list_available_datasets()
        if args.dataset in by_category:
            dataset_names = by_category[args.dataset]
        else:
            print(f"Unknown dataset or category: {args.dataset}")
            print(f"Available: {', '.join(DATASET_REGISTRY.keys())}")
            print(f"Categories: {', '.join(by_category.keys())}")
            sys.exit(1)

    for name in dataset_names:
        print(f"\n--- Loading {name} ---")
        try:
            if name == "tool_outputs":
                suite = load_tool_output_samples()
            else:
                suite = load_dataset_by_name(name, n=args.n)

            print(f"Loaded {len(suite)} cases")

            def progress(current: int, total: int, result: EvalResult) -> None:
                status = "PASS" if result.accuracy_preserved else "FAIL"
                compression = f"{result.compression_ratio:.0%}"
                print(f"  [{current}/{total}] {status} F1={result.f1_score:.2f} Comp={compression}")

            result = runner.run(suite, progress_callback=progress)
            all_results.append(result)
            print(f"\n{result.summary()}")

        except ImportError as e:
            print(f"Skipping {name}: {e}")
            print("  (Install with: pip install headroom-ai[evals])")
        except Exception as e:
            print(f"Error loading {name}: {e}")

    if not all_results:
        print("\nNo datasets were successfully loaded.")
        sys.exit(1)

    # Aggregate all results
    print("\n" + "=" * 60)
    print("OVERALL RESULTS")
    print("=" * 60)

    total_cases = sum(r.total_cases for r in all_results)
    total_passed = sum(r.passed_cases for r in all_results)
    total_original = sum(r.total_original_tokens for r in all_results)
    total_compressed = sum(r.total_compressed_tokens for r in all_results)

    if total_cases > 0:
        print(f"""
Total Cases:            {total_cases}
Passed:                 {total_passed} ({total_passed / total_cases:.1%})
Failed:                 {total_cases - total_passed}
Total Original Tokens:  {total_original:,}
Total Compressed:       {total_compressed:,}
Tokens Saved:           {total_original - total_compressed:,} ({(total_original - total_compressed) / total_original:.1%})
""")

    if args.output:
        # Save combined results
        import json

        output = {
            "suites": [r.to_dict() for r in all_results],
            "totals": {
                "cases": total_cases,
                "passed": total_passed,
                "accuracy_rate": total_passed / total_cases if total_cases else 0,
                "tokens_original": total_original,
                "tokens_compressed": total_compressed,
            },
        }
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Results saved to: {args.output}")


def cmd_suite(args: argparse.Namespace) -> None:
    """Run tiered evaluation suite."""
    from headroom.evals.reports.report_card import save_reports
    from headroom.evals.suite_runner import SuiteRunner

    tiers = list(range(1, args.tier + 1))

    print("=" * 60)
    print("HEADROOM EVALUATION SUITE")
    print("=" * 60)
    print(f"Model: {args.model}")
    print(f"Tiers: {tiers}")
    print(f"Budget: ${args.budget:.2f}")
    print(f"Port: {args.port}")
    print("=" * 60)

    runner = SuiteRunner(
        model=args.model,
        tiers=tiers,
        budget_usd=args.budget,
        headroom_port=args.port,
        auto_start_proxy=not args.no_proxy,
    )

    result = runner.run()

    # Save reports
    if args.output:
        paths = save_reports(result, args.output)
        print("\nReports saved:")
        for fmt, path in paths.items():
            print(f"  {fmt}: {path}")

    # CI mode: exit 1 if any benchmark failed
    if args.ci and not result.all_passed:
        failed = [b.name for b in result.benchmarks if not b.passed]
        print(f"\nCI FAILURE: {len(failed)} benchmark(s) failed: {', '.join(failed)}")
        sys.exit(1)

    if result.all_passed:
        print("\nAll benchmarks PASSED.")
    else:
        failed = [b.name for b in result.benchmarks if not b.passed]
        print(f"\nWARNING: {len(failed)} benchmark(s) failed: {', '.join(failed)}")
        sys.exit(1)


def cmd_compaction_compare(
    args: argparse.Namespace,
    _anthropic_client=None,
    _openai_client=None,
    _load_dataset=None,
) -> None:
    """Run a multi-arm compaction comparison sweep."""
    import dataclasses
    import json
    import sys
    from pathlib import Path

    from headroom.evals.runners.compaction_compare import (
        _VALID_ARMS,
        CompactionCompareConfig,
        CompactionCompareDriver,
    )

    # --- Parse arms ---
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    invalid = [a for a in arms if a not in _VALID_ARMS]
    if invalid:
        print(f"Error: unknown arm(s): {invalid}. Valid: {sorted(_VALID_ARMS)}", file=sys.stderr)
        sys.exit(1)

    # --- Build clients lazily ---
    needs_anthropic = (
        args.provider == "anthropic" or "anthropic_compact" in arms or "summary_prompt" in arms
    )
    needs_openai = args.provider == "openai" or "openai_compact" in arms

    if _anthropic_client is None and needs_anthropic:
        try:
            import anthropic as _anthropic_sdk

            # Long-context runs regularly trip the org-level 2M tokens/min cap.
            # The SDK default of 2 client-side retries is too small; bump to 10
            # so transient 429s get absorbed by the SDK's built-in `retry-after`
            # handling before our runner-level retry_on_rate_limit wrapper kicks in.
            _anthropic_client = _anthropic_sdk.Anthropic(max_retries=10)
        except ImportError:
            print(
                "Error: 'anthropic' SDK not installed. Run: pip install anthropic", file=sys.stderr
            )
            sys.exit(1)

    if _openai_client is None and needs_openai:
        try:
            import openai as _openai_sdk

            _openai_client = _openai_sdk.OpenAI()
        except ImportError:
            print("Error: 'openai' SDK not installed. Run: pip install openai", file=sys.stderr)
            sys.exit(1)

    # --- Load dataset ---
    if _load_dataset is None:
        from headroom.evals.datasets import load_dataset_by_name as _load_dataset

    extra_kwargs: dict = {}
    if args.dataset == "longmemeval" and getattr(args, "question_type", None):
        extra_kwargs["question_type"] = args.question_type

    if args.dataset == "longbench_v1_suite":
        suite = _load_dataset(args.dataset, n_per_task=args.n)
    else:
        suite = _load_dataset(args.dataset, n=args.n, **extra_kwargs)

    # --- Build config and driver ---
    # Use getattr with defaults for the new arm-specific flags so older
    # test fixtures that build a bare argparse.Namespace still work.
    config = CompactionCompareConfig(
        arms=arms,
        provider=args.provider,
        model=args.model,
        summary_model=args.summary_model,
        max_tokens=args.max_tokens,
        threshold=args.threshold,
        chunk_token_size=args.chunk_token_size,
        trigger_fill=args.trigger_fill,
        keep_recent=args.keep_recent,
        min_turn=args.min_turn,
        max_cycles=args.max_cycles,
        model_context_window=args.model_context_window,
        compact_v2_trigger_input_tokens=getattr(args, "compact_v2_trigger_input_tokens", 60_000),
        compact_v2_max_tokens=getattr(args, "compact_v2_max_tokens", 2048),
        session_memory_summary_model=getattr(
            args, "session_memory_summary_model", "claude-haiku-4-5-20251001"
        ),
        session_memory_max_summary_tokens=getattr(
            args, "session_memory_max_summary_tokens", 2048
        ),
        session_memory_max_answer_tokens=getattr(
            args, "session_memory_max_answer_tokens", 512
        ),
    )

    driver = CompactionCompareDriver(
        config=config,
        anthropic_client=_anthropic_client,
        openai_client=_openai_client,
    )

    # --- Run with per-case progress printing ---
    # Monkey-patch driver.run to intercept results as they're produced.
    # Simpler: just run normally and print after; driver.run collects all results.
    report = driver.run(suite)

    # Print per-case progress
    for arm in arms:
        arm_results = report.results.get(arm, [])
        for result in arm_results:
            print(
                f"[arm={arm} case={result.case_id}] "
                f"tokens={result.final_input_tokens} "
                f"ratio={result.compression_ratio:.3f} "
                f"latency={result.latency_ms:.0f}ms"
            )

    # --- Write output ---
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Serialize report: convert errors dict (tuple keys) to string keys
    results_dict = {
        arm: [dataclasses.asdict(r) for r in results] for arm, results in report.results.items()
    }
    errors_dict = {f"{arm}:{case_id}": msg for (arm, case_id), msg in report.errors.items()}
    report_data = {
        "suite_name": report.suite_name,
        "config": dataclasses.asdict(config),
        "results": results_dict,
        "errors": errors_dict,
    }
    with open(output_dir / "report.json", "w") as f:
        json.dump(report_data, f, indent=2)

    # --- Per-arm summary ---
    summary_lines = []
    for arm in arms:
        arm_results = report.results.get(arm, [])
        n_success = sum(1 for r in arm_results if not r.error)
        n_errors = len(arm_results) - n_success
        mean_ratio = (
            sum(r.compression_ratio for r in arm_results if not r.error) / n_success
            if n_success > 0
            else 0.0
        )
        mean_latency = (
            sum(r.latency_ms for r in arm_results if not r.error) / n_success
            if n_success > 0
            else 0.0
        )
        mean_compactions = (
            sum(r.n_compactions for r in arm_results if not r.error) / n_success
            if n_success > 0
            else 0.0
        )
        line = (
            f"{arm}: n_success={n_success} n_errors={n_errors} "
            f"mean_compression_ratio={mean_ratio:.3f} "
            f"mean_latency_ms={mean_latency:.1f} "
            f"mean_compaction_events={mean_compactions:.2f}"
        )
        summary_lines.append(line)

    summary_text = "\n".join(summary_lines) + "\n"
    with open(output_dir / "summary.txt", "w") as f:
        f.write(summary_text)
    print(summary_text, end="")

    # --- Warn if >50% per-arm error rate ---
    for arm in arms:
        arm_results = report.results.get(arm, [])
        if arm_results:
            n_errors = sum(1 for r in arm_results if r.error)
            if n_errors / len(arm_results) > 0.5:
                print(
                    f"WARNING: arm '{arm}' had {n_errors}/{len(arm_results)} errors (>{50}%)",
                    file=sys.stderr,
                )

    # --- Quality scoring (unless --no-judge) ---
    if not getattr(args, "no_judge", False):
        from headroom.evals.reports.compaction_compare_report import save_reports, score_report

        judge = create_anthropic_judge(model=getattr(args, "judge_model", "claude-haiku-4-5"))
        scored = score_report(report, suite, judge)
        paths = save_reports(scored, output_dir)
        print("\nScored reports written:")
        for fmt, path in paths.items():
            print(f"  {fmt}: {path}")
        # Print the headline table to stdout for immediate feedback
        md_text = (output_dir / "report.md").read_text()
        # Print up to the first blank line after the Results table
        in_results = False
        for line in md_text.splitlines():
            print(line)
            if line.startswith("## Results"):
                in_results = True
            elif in_results and line.startswith("## ") and not line.startswith("## Results"):
                break


def cmd_report(args: argparse.Namespace) -> None:
    """Generate HTML report from results."""
    import json

    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    with open(args.input) as f:
        data = json.load(f)

    # Generate HTML report
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Headroom Evaluation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1000px;
            margin: 40px auto;
            padding: 20px;
            background: #f8f9fa;
        }}
        h1 {{ color: #1a1a2e; margin-bottom: 10px; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        .summary {{
            background: white;
            padding: 24px;
            border-radius: 12px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .summary h2 {{ margin-top: 0; }}
        .metric {{
            display: inline-block;
            margin: 10px 20px 10px 0;
            padding: 12px 20px;
            background: #f0f0f0;
            border-radius: 8px;
        }}
        .metric .value {{ font-size: 24px; font-weight: bold; }}
        .metric .label {{ font-size: 12px; color: #666; }}
        .pass {{ color: #22c55e; }}
        .fail {{ color: #ef4444; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        th, td {{
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge.pass {{ background: #dcfce7; color: #166534; }}
        .badge.fail {{ background: #fee2e2; color: #991b1b; }}
        footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <h1>Headroom Compression Accuracy Report</h1>
    <p>Proving compression preserves LLM accuracy through before/after comparison.</p>

    <div class="summary">
        <h2>Overall Results</h2>
        <div class="metric">
            <div class="value">{data["totals"]["cases"]}</div>
            <div class="label">Total Cases</div>
        </div>
        <div class="metric">
            <div class="value {("pass" if data["totals"]["accuracy_rate"] > 0.9 else "fail")}">{data["totals"]["accuracy_rate"]:.1%}</div>
            <div class="label">Accuracy Preserved</div>
        </div>
        <div class="metric">
            <div class="value">{data["totals"]["tokens_original"] - data["totals"]["tokens_compressed"]:,}</div>
            <div class="label">Tokens Saved</div>
        </div>
        <div class="metric">
            <div class="value">{(data["totals"]["tokens_original"] - data["totals"]["tokens_compressed"]) / data["totals"]["tokens_original"]:.1%}</div>
            <div class="label">Compression Rate</div>
        </div>
    </div>
"""

    for suite in data.get("suites", []):
        pass_rate = suite["passed_cases"] / suite["total_cases"] if suite["total_cases"] > 0 else 0
        html += f"""
    <h2>{suite["suite_name"]}</h2>
    <p>
        <span class="badge {"pass" if pass_rate > 0.9 else "fail"}">{suite["passed_cases"]}/{suite["total_cases"]} passed</span>
        | F1: {suite["avg_f1_score"]:.3f}
        | Compression: {suite["avg_compression_ratio"]:.1%}
    </p>

    <table>
        <tr><th>Case ID</th><th>Status</th><th>F1 Score</th><th>Compression</th></tr>
"""
        for result in suite.get("results", [])[:20]:  # Limit to 20 per suite
            status = "PASS" if result["accuracy_preserved"] else "FAIL"
            status_class = "pass" if result["accuracy_preserved"] else "fail"
            html += f"""        <tr>
            <td>{result["case_id"]}</td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{result["f1_score"]:.3f}</td>
            <td>{result["compression_ratio"]:.1%}</td>
        </tr>
"""
        html += "    </table>\n"

    html += """
    <footer>
        <p>Generated by <strong>Headroom Evaluation Framework</strong></p>
        <p>Install: <code>pip install headroom-ai[evals]</code></p>
    </footer>
</body>
</html>
"""

    output_path = args.output or args.input.replace(".json", ".html")
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Report generated: {output_path}")


def main() -> None:
    # Load API keys from .env
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Headroom Evaluation Framework - Prove compression preserves accuracy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m headroom.evals quick                        # Quick 5-sample check
  python -m headroom.evals quick -n 10                  # Quick 10-sample check
  python -m headroom.evals list                         # List available datasets
  python -m headroom.evals benchmark                    # Run tool_outputs benchmark
  python -m headroom.evals benchmark --dataset hotpotqa -n 50
  python -m headroom.evals benchmark --dataset rag      # Run all RAG datasets
  python -m headroom.evals benchmark --dataset all      # Run ALL datasets
  python -m headroom.evals suite --tier 1               # Run Tier 1 suite (~$3)
  python -m headroom.evals suite --tier 2               # Run Tiers 1+2 (~$8)
  python -m headroom.evals suite --tier 1 --ci          # CI mode (exit 1 on fail)
  python -m headroom.evals report -i results.json       # Generate HTML report
  python -m headroom.evals compaction-compare --dataset longmemeval -n 50 --arms baseline,headroom_default --provider anthropic --model claude-sonnet-4-5-20250514 -o eval_results/

Available datasets by category:
  RAG:          hotpotqa, natural_questions, triviaqa, msmarco, squad
  Long Context: longbench, narrativeqa
  Tool Use:     bfcl, toolbench, tool_outputs
  Code:         codesearchnet, humaneval

Install dependencies:
  pip install headroom-ai[all]
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Quick command
    quick_parser = subparsers.add_parser("quick", help="Run quick sanity check")
    quick_parser.add_argument("-n", type=int, default=5, help="Number of samples")
    quick_parser.add_argument("--provider", default="anthropic", help="LLM provider")
    quick_parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Model to use")
    quick_parser.add_argument("-o", "--output", help="Output file for results (JSON)")
    quick_parser.set_defaults(func=cmd_quick)

    # List command
    list_parser = subparsers.add_parser("list", help="List available datasets")
    list_parser.set_defaults(func=cmd_list)

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Run full benchmark suite")
    bench_parser.add_argument("-n", type=int, default=20, help="Samples per dataset")
    bench_parser.add_argument(
        "--dataset",
        default="tool_outputs",
        help="Dataset name, category (rag, tool_use, code, long_context), 'quick', or 'all'",
    )
    bench_parser.add_argument("--provider", default="anthropic", help="LLM provider")
    bench_parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Model to use")
    bench_parser.add_argument("--semantic", action="store_true", help="Enable semantic similarity")
    bench_parser.add_argument("-o", "--output", help="Output file for results (JSON)")
    bench_parser.set_defaults(func=cmd_benchmark)

    # Suite command
    suite_parser = subparsers.add_parser(
        "suite", help="Run tiered evaluation suite (the main entrypoint)"
    )
    suite_parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        default=1,
        help="Max tier to run: 1=core (~$3), 2=extended (~$8), 3=full (~$17)",
    )
    suite_parser.add_argument("--model", default="gpt-4o-mini", help="Model (default: gpt-4o-mini)")
    suite_parser.add_argument(
        "--budget", type=float, default=20.0, help="Budget in USD (default: $20)"
    )
    suite_parser.add_argument("--port", type=int, default=8787, help="Headroom proxy port")
    suite_parser.add_argument("--ci", action="store_true", help="CI mode: exit 1 on any failure")
    suite_parser.add_argument("--no-proxy", action="store_true", help="Don't auto-start proxy")
    suite_parser.add_argument("-o", "--output", help="Output directory for reports")
    suite_parser.set_defaults(func=cmd_suite)

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate HTML report")
    report_parser.add_argument("-i", "--input", required=True, help="Input JSON results file")
    report_parser.add_argument("-o", "--output", help="Output HTML file")
    report_parser.set_defaults(func=cmd_report)

    # Compaction-compare command
    cc_parser = subparsers.add_parser(
        "compaction-compare",
        help="Cross-arm comparison of compression / compaction strategies on long-context datasets",
    )
    cc_parser.add_argument(
        "--dataset", default="longmemeval", help="Dataset name from DATASET_REGISTRY"
    )
    cc_parser.add_argument("-n", "--n", type=int, default=50, dest="n", help="Number of cases")
    cc_parser.add_argument(
        "--question-type",
        dest="question_type",
        default=None,
        help=(
            "LongMemEval-only: filter to a single question_type. One of: "
            "multi-session, temporal-reasoning, knowledge-update, "
            "single-session-user, single-session-assistant, "
            "single-session-preference. Ignored for other datasets."
        ),
    )
    cc_parser.add_argument(
        "--arms",
        default="baseline,headroom_default,anthropic_compact,summary_prompt",
        help=(
            "Comma-separated arm names. Valid: baseline, headroom_default, "
            "anthropic_compact (old tool_runner path), anthropic_compact_v2 "
            "(server-side compact_20260112, requires Sonnet 4.6+), "
            "anthropic_session_memory (cookbook pattern, requires Sonnet 4.6+), "
            "openai_compact, summary_prompt"
        ),
    )
    cc_parser.add_argument(
        "--threshold", type=int, default=50000, help="Token threshold for compaction arms"
    )
    cc_parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    cc_parser.add_argument("--model", required=True, help="Answer model id")
    cc_parser.add_argument("--summary-model", default="claude-haiku-4-5", dest="summary_model")
    cc_parser.add_argument("--chunk-token-size", type=int, default=10000, dest="chunk_token_size")
    cc_parser.add_argument("--max-tokens", type=int, default=1024, dest="max_tokens")
    cc_parser.add_argument("--trigger-fill", type=float, default=0.70, dest="trigger_fill")
    cc_parser.add_argument("--keep-recent", type=int, default=4, dest="keep_recent")
    cc_parser.add_argument("--min-turn", type=int, default=3, dest="min_turn")
    cc_parser.add_argument("--max-cycles", type=int, default=3, dest="max_cycles")
    cc_parser.add_argument(
        "--model-context-window", type=int, default=200000, dest="model_context_window"
    )
    # --- Knobs specific to anthropic_compact_v2 ---
    cc_parser.add_argument(
        "--compact-v2-trigger",
        type=int,
        default=60_000,
        dest="compact_v2_trigger_input_tokens",
        help=(
            "anthropic_compact_v2: input_tokens threshold at which the "
            "server triggers compact_20260112. Min 50000. Default 60000 "
            "(fires on every LongMemEval case)."
        ),
    )
    cc_parser.add_argument(
        "--compact-v2-max-tokens",
        type=int,
        default=2048,
        dest="compact_v2_max_tokens",
        help=(
            "anthropic_compact_v2: max output tokens. Bounds both the "
            "compaction summary and the final answer. 2048 is the "
            "minimum that avoids truncating the summary."
        ),
    )
    # --- Knobs specific to anthropic_session_memory ---
    cc_parser.add_argument(
        "--session-memory-summary-model",
        default="claude-haiku-4-5-20251001",
        dest="session_memory_summary_model",
        help="anthropic_session_memory: model used for the session memory summary call (default Haiku 4.5)",
    )
    cc_parser.add_argument(
        "--session-memory-max-summary-tokens",
        type=int,
        default=2048,
        dest="session_memory_max_summary_tokens",
    )
    cc_parser.add_argument(
        "--session-memory-max-answer-tokens",
        type=int,
        default=512,
        dest="session_memory_max_answer_tokens",
    )
    cc_parser.add_argument("-o", "--output", required=True, help="Output directory")
    cc_parser.add_argument(
        "--judge-model",
        default="claude-haiku-4-5",
        dest="judge_model",
        help="Anthropic model to use for quality scoring (default: claude-haiku-4-5)",
    )
    cc_parser.add_argument(
        "--no-judge",
        action="store_true",
        dest="no_judge",
        default=False,
        help="Skip quality scoring (useful for cheap dry runs)",
    )
    cc_parser.set_defaults(func=cmd_compaction_compare)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
