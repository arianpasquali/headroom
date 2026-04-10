"""Tests for cmd_compaction_compare CLI subcommand.

Uses dependency injection (_anthropic_client, _openai_client, _load_dataset)
to avoid real API calls. Tests call cmd_compaction_compare directly with a
constructed argparse.Namespace — no main() invocation needed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fake clients (mirror pattern from test_compaction_compare.py)
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
# Fake dataset loader
# ---------------------------------------------------------------------------


def _make_fake_suite(n: int = 2):
    import json as _json

    from headroom.evals.core import EvalCase, EvalSuite

    cases = []
    for i in range(n):
        sessions = [{"session_id": i, "messages": [f"event {i}"]}]
        context = _json.dumps({"haystack_sessions": sessions})
        cases.append(EvalCase(id=f"case_{i}", context=context, query="What happened?"))
    return EvalSuite(name="test_suite", cases=cases)


def _fake_load_dataset(name: str, **kwargs: Any):
    return _make_fake_suite(n=kwargs.get("n", 2))


# ---------------------------------------------------------------------------
# Default args helper
# ---------------------------------------------------------------------------


def _make_args(**overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "dataset": "longmemeval",
        "n": 2,
        "arms": "baseline,headroom_default",
        "threshold": 50000,
        "provider": "anthropic",
        "model": "claude-test",
        "summary_model": "claude-haiku-4-5",
        "chunk_token_size": 10000,
        "max_tokens": 1024,
        "trigger_fill": 0.70,
        "keep_recent": 4,
        "min_turn": 3,
        "max_cycles": 3,
        "model_context_window": 200000,
        "output": None,  # will be overridden by tests
        "no_judge": True,  # default to True so existing tests don't make API calls
        "judge_model": "claude-haiku-4-5",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCmdCompactionCompare:
    def test_writes_report_json_to_output_dir(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(output=str(tmp_path))
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        report_path = tmp_path / "report.json"
        assert report_path.exists(), "report.json should be written"
        data = json.loads(report_path.read_text())
        assert "results" in data
        assert "config" in data

    def test_writes_summary_txt_to_output_dir(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(output=str(tmp_path))
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        summary_path = tmp_path / "summary.txt"
        assert summary_path.exists(), "summary.txt should be written"
        text = summary_path.read_text()
        assert "baseline" in text
        assert "headroom_default" in text

    def test_arms_parsed_from_comma_separated_string(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(output=str(tmp_path), arms="baseline")
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        data = json.loads((tmp_path / "report.json").read_text())
        # Only "baseline" arm should appear in results
        assert list(data["results"].keys()) == ["baseline"]

    def test_invalid_arm_name_raises_clean_error(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(output=str(tmp_path), arms="baseline,totally_invalid_arm")
        with pytest.raises((ValueError, SystemExit)):
            cmd_compaction_compare(
                args,
                _anthropic_client=_FakeAnthropicClient(),
                _load_dataset=_fake_load_dataset,
            )

    def test_creates_output_directory_if_missing(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        nested = tmp_path / "deep" / "nested" / "dir"
        assert not nested.exists()

        args = _make_args(output=str(nested))
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        assert nested.exists()
        assert (nested / "report.json").exists()

    def test_per_arm_summary_includes_means(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(output=str(tmp_path), arms="baseline")
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        summary_path = tmp_path / "summary.txt"
        text = summary_path.read_text()
        # Summary must mention key metrics
        assert "ratio" in text.lower() or "compression" in text.lower()
        assert "latency" in text.lower()

    def test_handles_empty_suite_gracefully(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare
        from headroom.evals.core import EvalSuite

        def _empty_loader(name: str, **kwargs: Any):
            return EvalSuite(name="empty_suite", cases=[])

        args = _make_args(output=str(tmp_path), arms="baseline")
        # Should not raise
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_empty_loader,
        )

        data = json.loads((tmp_path / "report.json").read_text())
        assert data["results"]["baseline"] == []

    def test_openai_provider_uses_openai_client(self, tmp_path):
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(
            output=str(tmp_path),
            arms="baseline",
            provider="openai",
        )
        cmd_compaction_compare(
            args,
            _openai_client=_FakeOpenAIClient(),
            _load_dataset=_fake_load_dataset,
        )

        data = json.loads((tmp_path / "report.json").read_text())
        assert "baseline" in data["results"]


# ---------------------------------------------------------------------------
# New tests: --no-judge and judge-on path
# ---------------------------------------------------------------------------


class TestJudgeIntegration:
    def test_no_judge_flag_skips_scoring(self, tmp_path):
        """--no-judge should skip report.md and scored_report.json."""
        from headroom.evals.__main__ import cmd_compaction_compare

        args = _make_args(output=str(tmp_path), no_judge=True)
        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        # Raw outputs must still exist
        assert (tmp_path / "report.json").exists()
        assert (tmp_path / "summary.txt").exists()
        # Scored outputs should NOT be written
        assert not (tmp_path / "report.md").exists()
        assert not (tmp_path / "scored_report.json").exists()

    def test_judge_on_writes_report_md(self, tmp_path, monkeypatch):
        """Without --no-judge, report.md and scored_report.json should be written."""
        from headroom.evals import __main__ as cli_module

        fake_judge_fn = lambda q, gt, pred: (5.0, "ok")  # noqa: E731

        def _fake_create_anthropic_judge(model: str = "claude-haiku-4-5", **kwargs):
            return fake_judge_fn

        monkeypatch.setattr(cli_module, "create_anthropic_judge", _fake_create_anthropic_judge)

        args = _make_args(
            output=str(tmp_path),
            no_judge=False,
            judge_model="claude-haiku-4-5",
        )
        from headroom.evals.__main__ import cmd_compaction_compare

        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_fake_load_dataset,
        )

        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "scored_report.json").exists()
        # Raw report.json should also still exist
        assert (tmp_path / "report.json").exists()

    def test_judge_on_summary_includes_quality(self, tmp_path, monkeypatch):
        """When judge runs, summary.txt should mention quality (enriched format)."""
        from headroom.evals import __main__ as cli_module

        fake_judge_fn = lambda q, gt, pred: (4.0, "good")  # noqa: E731

        def _fake_create_anthropic_judge(model: str = "claude-haiku-4-5", **kwargs):
            return fake_judge_fn

        monkeypatch.setattr(cli_module, "create_anthropic_judge", _fake_create_anthropic_judge)

        # Give cases ground_truth so judge is actually called
        import json as _json

        from headroom.evals.core import EvalCase, EvalSuite

        def _loader_with_gt(name: str, **kwargs):
            cases = []
            for i in range(2):
                sessions = [{"session_id": i, "messages": [f"event {i}"]}]
                context = _json.dumps({"haystack_sessions": sessions})
                cases.append(
                    EvalCase(
                        id=f"case_{i}",
                        context=context,
                        query="What happened?",
                        ground_truth=f"answer_{i}",
                    )
                )
            return EvalSuite(name="test_suite", cases=cases)

        args = _make_args(
            output=str(tmp_path),
            no_judge=False,
            judge_model="claude-haiku-4-5",
        )
        from headroom.evals.__main__ import cmd_compaction_compare

        cmd_compaction_compare(
            args,
            _anthropic_client=_FakeAnthropicClient(),
            _load_dataset=_loader_with_gt,
        )

        summary = (tmp_path / "summary.txt").read_text()
        # Enriched summary should contain quality info
        assert "quality" in summary.lower()
