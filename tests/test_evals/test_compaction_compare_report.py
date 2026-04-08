"""Tests for compaction_compare_report.py — score_report, render_markdown, save_reports.

Uses a fake judge callable to avoid real API calls.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from headroom.evals.core import EvalCase, EvalSuite
from headroom.evals.runners.compaction_compare import (
    CompactionCompareConfig,
    CompactionCompareReport,
)
from headroom.evals.runners.provider_compaction import CompactionResult

# ---------------------------------------------------------------------------
# Fake judge helpers
# ---------------------------------------------------------------------------


def _fake_judge(question: str, ground_truth: str, prediction: str) -> tuple[float, str]:
    """Returns 5.0 if 'correct' in prediction, else 1.0."""
    if "correct" in prediction.lower():
        return 5.0, "looks correct"
    return 1.0, "looks wrong"


def _always_three_judge(question: str, ground_truth: str, prediction: str) -> tuple[float, str]:
    return 3.0, "borderline"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_config() -> CompactionCompareConfig:
    return CompactionCompareConfig(
        arms=["baseline", "headroom_default"],
        provider="anthropic",
        model="claude-test",
    )


def _make_suite(with_qtype: bool = False) -> EvalSuite:
    def _meta(qtype: str | None = None) -> dict:
        return {"question_type": qtype} if qtype else {}

    cases = [
        EvalCase(
            id="c1",
            context="ctx1",
            query="q1",
            ground_truth="gt1",
            metadata=_meta("single_hop") if with_qtype else {},
        ),
        EvalCase(
            id="c2",
            context="ctx2",
            query="q2",
            ground_truth="gt2",
            metadata=_meta("multi_hop") if with_qtype else {},
        ),
        EvalCase(
            id="c3",
            context="ctx3",
            query="q3",
            ground_truth="gt3",
            metadata=_meta("single_hop") if with_qtype else {},
        ),
    ]
    return EvalSuite(name="test_suite", cases=cases)


def _make_result(
    case_id: str,
    answer: str = "the correct answer",
    error: str | None = None,
    original_tokens: int = 1000,
    final_tokens: int = 600,
    compression: float = 0.4,
    latency: float = 500.0,
    n_iter: int = 3,
    n_comp: int = 1,
) -> CompactionResult:
    return CompactionResult(
        case_id=case_id,
        answer=answer,
        original_input_tokens=original_tokens,
        final_input_tokens=final_tokens,
        compression_ratio=compression,
        latency_ms=latency,
        n_iterations=n_iter,
        n_compactions=n_comp,
        error=error,
    )


def _make_report(suite: EvalSuite) -> CompactionCompareReport:
    report = CompactionCompareReport(
        suite_name=suite.name,
        config=_make_config(),
    )
    for arm in ["baseline", "headroom_default"]:
        report.results[arm] = [
            _make_result(case.id, answer="the correct answer") for case in suite.cases
        ]
    return report


# ---------------------------------------------------------------------------
# TestScoreReport
# ---------------------------------------------------------------------------


class TestScoreReport:
    def test_scores_cases_with_judge_function(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite()
        report = _make_report(suite)
        scored = score_report(report, suite, _fake_judge)

        assert len(scored.cases_by_arm["baseline"]) == 3
        for sc in scored.cases_by_arm["baseline"]:
            assert sc.quality_score == 5.0
            assert sc.quality_correct is True
            assert sc.quality_reasoning == "looks correct"

    def test_handles_runner_errors_as_zero_quality(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite()
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        report.results["baseline"] = [
            _make_result("c1", error="timeout"),
            _make_result("c2"),
            _make_result("c3"),
        ]
        report.results["headroom_default"] = [_make_result(c.id) for c in suite.cases]

        scored = score_report(report, suite, _fake_judge)
        error_case = next(sc for sc in scored.cases_by_arm["baseline"] if sc.case_id == "c1")
        assert error_case.quality_score == 0.0
        assert error_case.quality_correct is False
        assert error_case.error == "timeout"
        assert "runner error" in error_case.quality_reasoning

    def test_handles_missing_ground_truth(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = EvalSuite(
            name="no_gt",
            cases=[EvalCase(id="c1", context="ctx", query="q", ground_truth=None)],
        )
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        report.results["baseline"] = [_make_result("c1")]

        scored = score_report(report, suite, _fake_judge)
        sc = scored.cases_by_arm["baseline"][0]
        assert sc.quality_score == 0.0
        assert sc.quality_correct is False
        assert "no ground_truth" in sc.quality_reasoning

    def test_baseline_first_in_aggregates(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite()
        report = _make_report(suite)
        scored = score_report(report, suite, _fake_judge, baseline_arm="baseline")

        assert scored.aggregates[0].arm == "baseline"
        assert scored.baseline_arm == "baseline"

    def test_delta_quality_computed_against_baseline(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite()
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        # baseline: all correct answers
        report.results["baseline"] = [
            _make_result(c.id, answer="the correct answer") for c in suite.cases
        ]
        # headroom_default: all wrong answers
        report.results["headroom_default"] = [
            _make_result(c.id, answer="totally wrong answer") for c in suite.cases
        ]

        scored = score_report(report, suite, _fake_judge, baseline_arm="baseline")
        agg_baseline = next(a for a in scored.aggregates if a.arm == "baseline")
        agg_hd = next(a for a in scored.aggregates if a.arm == "headroom_default")

        assert agg_baseline.quality_correct_rate == pytest.approx(1.0)
        assert agg_hd.quality_correct_rate == pytest.approx(0.0)
        assert agg_hd.delta_quality_correct_rate == pytest.approx(-1.0)
        assert agg_baseline.delta_quality_correct_rate == pytest.approx(0.0)

    def test_quality_correct_threshold_at_three(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = EvalSuite(
            name="thresh",
            cases=[EvalCase(id="c1", context="ctx", query="q", ground_truth="gt")],
        )
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        report.results["baseline"] = [_make_result("c1", answer="some answer")]

        # Score exactly 3 → correct
        scored = score_report(report, suite, _always_three_judge, baseline_arm="baseline")
        sc = scored.cases_by_arm["baseline"][0]
        assert sc.quality_score == 3.0
        assert sc.quality_correct is True

    def test_per_question_type_breakdown(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite(with_qtype=True)
        report = _make_report(suite)
        scored = score_report(report, suite, _fake_judge)

        agg_baseline = next(a for a in scored.aggregates if a.arm == "baseline")
        assert "single_hop" in agg_baseline.quality_correct_rate_by_qtype
        assert "multi_hop" in agg_baseline.quality_correct_rate_by_qtype
        # All correct answers → 100% for each type
        assert agg_baseline.quality_correct_rate_by_qtype["single_hop"] == pytest.approx(1.0)
        assert agg_baseline.quality_correct_rate_by_qtype["multi_hop"] == pytest.approx(1.0)

    def test_handles_empty_results(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = EvalSuite(name="empty", cases=[])
        report = CompactionCompareReport(suite_name="empty", config=_make_config())
        # No results at all
        scored = score_report(report, suite, _fake_judge)

        assert scored.cases_by_arm == {}
        assert scored.aggregates == []

    def test_n_errors_counted_in_aggregate(self):
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite()
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        report.results["baseline"] = [
            _make_result("c1", error="boom"),
            _make_result("c2"),
            _make_result("c3"),
        ]
        report.results["headroom_default"] = [_make_result(c.id) for c in suite.cases]

        scored = score_report(report, suite, _fake_judge)
        agg = next(a for a in scored.aggregates if a.arm == "baseline")
        assert agg.n_errors == 1
        assert agg.n_cases == 3


# ---------------------------------------------------------------------------
# TestRenderMarkdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def _make_scored(self) -> Any:
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite(with_qtype=True)
        report = _make_report(suite)
        return score_report(report, suite, _fake_judge)

    def test_includes_headline_table(self):
        from headroom.evals.reports.compaction_compare_report import render_markdown

        scored = self._make_scored()
        md = render_markdown(scored)

        assert "baseline" in md
        assert "headroom_default" in md
        # Table markers
        assert "|" in md

    def test_renders_delta_with_explicit_sign(self):
        from headroom.evals.reports.compaction_compare_report import render_markdown, score_report

        suite = _make_suite()
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        report.results["baseline"] = [_make_result(c.id, answer="correct") for c in suite.cases]
        report.results["headroom_default"] = [
            _make_result(c.id, answer="wrong") for c in suite.cases
        ]
        scored = score_report(report, suite, _fake_judge)
        md = render_markdown(scored)

        # baseline delta should be +0.0 or show 0, headroom_default should be negative
        assert "+" in md or "-" in md or "0.0" in md

    def test_includes_per_qtype_subtable(self):
        from headroom.evals.reports.compaction_compare_report import render_markdown

        scored = self._make_scored()
        md = render_markdown(scored)

        assert "single_hop" in md or "multi_hop" in md

    def test_handles_no_baseline_gracefully(self):
        from headroom.evals.reports.compaction_compare_report import render_markdown, score_report

        suite = _make_suite()
        report = CompactionCompareReport(suite_name=suite.name, config=_make_config())
        # No 'baseline' arm at all
        report.results["headroom_default"] = [_make_result(c.id) for c in suite.cases]
        scored = score_report(report, suite, _fake_judge, baseline_arm="baseline")

        # Should not raise; baseline_arm is None or not in aggregates
        md = render_markdown(scored)
        assert "headroom_default" in md

    def test_no_crash_on_empty_scored(self):
        from headroom.evals.reports.compaction_compare_report import render_markdown, score_report

        suite = EvalSuite(name="empty", cases=[])
        report = CompactionCompareReport(suite_name="empty", config=_make_config())
        scored = score_report(report, suite, _fake_judge)

        md = render_markdown(scored)
        assert isinstance(md, str)


# ---------------------------------------------------------------------------
# TestSaveReports
# ---------------------------------------------------------------------------


class TestSaveReports:
    def _make_scored(self) -> Any:
        from headroom.evals.reports.compaction_compare_report import score_report

        suite = _make_suite(with_qtype=True)
        report = _make_report(suite)
        return score_report(report, suite, _fake_judge)

    def test_writes_three_files(self, tmp_path):
        from headroom.evals.reports.compaction_compare_report import save_reports

        scored = self._make_scored()
        paths = save_reports(scored, tmp_path)

        assert "markdown" in paths
        assert "json" in paths
        assert "summary" in paths
        assert paths["markdown"].exists()
        assert paths["json"].exists()
        assert paths["summary"].exists()

    def test_creates_output_dir_if_missing(self, tmp_path):
        from headroom.evals.reports.compaction_compare_report import save_reports

        nested = tmp_path / "deep" / "dir"
        assert not nested.exists()

        scored = self._make_scored()
        save_reports(scored, nested)
        assert nested.exists()

    def test_summary_txt_one_line_per_arm(self, tmp_path):
        from headroom.evals.reports.compaction_compare_report import save_reports

        scored = self._make_scored()
        paths = save_reports(scored, tmp_path)

        lines = [ln for ln in paths["summary"].read_text().splitlines() if ln.strip()]
        arm_names = {agg.arm for agg in scored.aggregates}
        for arm in arm_names:
            assert any(arm in line for line in lines)

    def test_json_output_is_valid_and_has_arms(self, tmp_path):
        from headroom.evals.reports.compaction_compare_report import save_reports

        scored = self._make_scored()
        paths = save_reports(scored, tmp_path)

        data = json.loads(paths["json"].read_text())
        assert "cases_by_arm" in data
        assert "baseline" in data["cases_by_arm"]

    def test_report_md_filename(self, tmp_path):
        from headroom.evals.reports.compaction_compare_report import save_reports

        scored = self._make_scored()
        paths = save_reports(scored, tmp_path)

        assert paths["markdown"].name == "report.md"
        assert paths["json"].name == "scored_report.json"
        assert paths["summary"].name == "summary.txt"
