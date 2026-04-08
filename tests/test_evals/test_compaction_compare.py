"""Tests for CompactionCompareDriver and related types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fake clients
# ---------------------------------------------------------------------------


@dataclass
class _FakeAnthropicContent:
    text: str


@dataclass
class _FakeAnthropicMessage:
    content: list[_FakeAnthropicContent]


class _FakeAnthropicMessages:
    def __init__(self, answer: str = "fake-answer") -> None:
        self._answer = answer
        self.call_count: int = 0

    def create(self, **kwargs: Any) -> _FakeAnthropicMessage:
        self.call_count += 1
        return _FakeAnthropicMessage(content=[_FakeAnthropicContent(text=self._answer)])


class _FakeAnthropicClient:
    def __init__(self, answer: str = "fake-answer") -> None:
        self.messages = _FakeAnthropicMessages(answer=answer)


@dataclass
class _FakeOpenAIResponse:
    output_text: str
    id: str = "resp-123"

    class _Usage:
        input_tokens: int = 5

    usage = _Usage()


class _FakeOpenAIResponses:
    def __init__(self, answer: str = "oai-answer") -> None:
        self._answer = answer

    def create(self, **kwargs: Any) -> _FakeOpenAIResponse:
        return _FakeOpenAIResponse(output_text=self._answer)

    def compact(self, **kwargs: Any) -> _FakeOpenAIResponse:
        return _FakeOpenAIResponse(output_text="compacted")


class _FakeOpenAIClient:
    def __init__(self, answer: str = "oai-answer") -> None:
        self.responses = _FakeOpenAIResponses(answer=answer)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_eval_case(case_id: str = "c1", query: str = "What happened?") -> Any:
    from headroom.evals.core import EvalCase

    sessions = [{"session_id": i, "messages": [f"event {i}"]} for i in range(2)]
    context = json.dumps({"haystack_sessions": sessions})
    return EvalCase(id=case_id, context=context, query=query)


def _make_suite(n: int = 2) -> Any:
    from headroom.evals.core import EvalSuite

    suite = EvalSuite(name="test-suite")
    for i in range(n):
        suite.add_case(_make_eval_case(case_id=f"case-{i}"))
    return suite


# ---------------------------------------------------------------------------
# TestCompactionCompareConfig
# ---------------------------------------------------------------------------


class TestCompactionCompareConfig:
    def test_valid_config_anthropic(self) -> None:
        from headroom.evals.runners.compaction_compare import CompactionCompareConfig

        cfg = CompactionCompareConfig(
            arms=["baseline", "headroom_default"],
            provider="anthropic",
            model="claude-haiku-4-5",
        )
        assert cfg.provider == "anthropic"
        assert cfg.arms == ["baseline", "headroom_default"]

    def test_valid_config_openai(self) -> None:
        from headroom.evals.runners.compaction_compare import CompactionCompareConfig

        cfg = CompactionCompareConfig(
            arms=["baseline"],
            provider="openai",
            model="gpt-4o-mini",
        )
        assert cfg.provider == "openai"
        assert cfg.max_tokens == 1024  # default

    def test_default_values(self) -> None:
        from headroom.evals.runners.compaction_compare import CompactionCompareConfig

        cfg = CompactionCompareConfig(
            arms=["baseline"],
            provider="anthropic",
            model="claude-haiku-4-5",
        )
        assert cfg.threshold == 50_000
        assert cfg.chunk_token_size == 10_000
        assert cfg.trigger_fill == 0.70
        assert cfg.keep_recent == 4
        assert cfg.min_turn == 3
        assert cfg.max_cycles == 3
        assert cfg.model_context_window == 200_000


# ---------------------------------------------------------------------------
# TestCompactionCompareDriver
# ---------------------------------------------------------------------------


class TestCompactionCompareDriver:
    def test_runs_baseline_arm(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline"], provider="anthropic", model="claude-haiku-4-5"
        )
        driver = CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())
        suite = _make_suite(n=2)
        report = driver.run(suite)

        assert "baseline" in report.results
        assert len(report.results["baseline"]) == 2

    def test_runs_multiple_arms_in_order(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline", "headroom_default"],
            provider="anthropic",
            model="claude-haiku-4-5",
        )
        driver = CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())
        suite = _make_suite(n=2)
        report = driver.run(suite)

        assert set(report.results.keys()) == {"baseline", "headroom_default"}
        assert len(report.results["baseline"]) == 2
        assert len(report.results["headroom_default"]) == 2

    def test_invalid_arm_name_raises(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline", "nonexistent_arm"],  # type: ignore[list-item]
            provider="anthropic",
            model="claude-haiku-4-5",
        )
        with pytest.raises(ValueError, match="nonexistent_arm"):
            CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())

    def test_openai_compact_with_anthropic_provider_raises(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["openai_compact"],
            provider="anthropic",  # incompatible
            model="claude-haiku-4-5",
        )
        with pytest.raises(ValueError):
            CompactionCompareDriver(
                cfg,
                anthropic_client=_FakeAnthropicClient(),
                openai_client=_FakeOpenAIClient(),
            )

    def test_anthropic_compact_with_openai_provider_raises(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["anthropic_compact"],
            provider="openai",  # incompatible
            model="gpt-4o-mini",
        )
        with pytest.raises(ValueError):
            CompactionCompareDriver(
                cfg,
                anthropic_client=_FakeAnthropicClient(),
                openai_client=_FakeOpenAIClient(),
            )

    def test_missing_required_client_raises(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline"],
            provider="anthropic",
            model="claude-haiku-4-5",
        )
        with pytest.raises(ValueError, match="anthropic_client"):
            CompactionCompareDriver(cfg, anthropic_client=None)

    def test_missing_openai_client_raises(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline"],
            provider="openai",
            model="gpt-4o-mini",
        )
        with pytest.raises(ValueError, match="openai_client"):
            CompactionCompareDriver(cfg, openai_client=None)

    def test_per_arm_error_handling_does_not_fail_whole_run(self) -> None:
        """If one runner raises, errors are captured and other arms still complete."""
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )
        from headroom.evals.runners.direct_runners import BaselineRunner

        # Patch BaselineRunner.run to raise on the first call
        original_run = BaselineRunner.run
        call_count = {"n": 0}

        def _failing_run(self: Any, case: Any) -> Any:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Simulated LLM failure")
            return original_run(self, case)

        BaselineRunner.run = _failing_run  # type: ignore[method-assign]

        try:
            cfg = CompactionCompareConfig(
                arms=["baseline", "headroom_default"],
                provider="anthropic",
                model="claude-haiku-4-5",
            )
            driver = CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())
            suite = _make_suite(n=2)
            report = driver.run(suite)

            # The error should be recorded
            error_keys = list(report.errors.keys())
            assert len(error_keys) >= 1
            arm, case_id = error_keys[0]
            assert arm == "baseline"
            assert "Simulated LLM failure" in report.errors[(arm, case_id)]

            # headroom_default should still have results
            assert "headroom_default" in report.results
            assert len(report.results["headroom_default"]) == 2

        finally:
            BaselineRunner.run = original_run  # type: ignore[method-assign]

    def test_returns_compaction_compare_report(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
            CompactionCompareReport,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline"], provider="anthropic", model="claude-haiku-4-5"
        )
        driver = CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())
        suite = _make_suite(n=1)
        report = driver.run(suite)

        assert isinstance(report, CompactionCompareReport)
        assert report.suite_name == "test-suite"
        assert report.config is cfg

    def test_results_keyed_by_arm_name(self) -> None:
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )

        cfg = CompactionCompareConfig(
            arms=["baseline", "headroom_default"],
            provider="anthropic",
            model="claude-haiku-4-5",
        )
        driver = CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())
        suite = _make_suite(n=3)
        report = driver.run(suite)

        for arm in ["baseline", "headroom_default"]:
            assert arm in report.results
            assert len(report.results[arm]) == 3
            for res in report.results[arm]:
                assert res.case_id in {f"case-{i}" for i in range(3)}

    def test_error_result_has_error_field(self) -> None:
        """A failed case produces a CompactionResult with error field set."""
        from headroom.evals.runners.compaction_compare import (
            CompactionCompareConfig,
            CompactionCompareDriver,
        )
        from headroom.evals.runners.direct_runners import BaselineRunner

        original_run = BaselineRunner.run

        def _always_fail(self: Any, case: Any) -> Any:
            raise ValueError("always fails")

        BaselineRunner.run = _always_fail  # type: ignore[method-assign]

        try:
            cfg = CompactionCompareConfig(
                arms=["baseline"],
                provider="anthropic",
                model="claude-haiku-4-5",
            )
            driver = CompactionCompareDriver(cfg, anthropic_client=_FakeAnthropicClient())
            suite = _make_suite(n=1)
            report = driver.run(suite)

            assert len(report.results["baseline"]) == 1
            result = report.results["baseline"][0]
            assert result.error is not None
            assert "always fails" in result.error
        finally:
            BaselineRunner.run = original_run  # type: ignore[method-assign]
