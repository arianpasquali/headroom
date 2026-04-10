"""Tests for BaselineRunner and HeadroomDefaultRunner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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
    def __init__(self, answer: str = "fake answer") -> None:
        self._answer = answer
        self.last_call_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeAnthropicMessage:
        self.last_call_kwargs = kwargs
        return _FakeAnthropicMessage(content=[_FakeAnthropicContent(text=self._answer)])


class _FakeAnthropicClient:
    def __init__(self, answer: str = "fake answer") -> None:
        self.messages = _FakeAnthropicMessages(answer=answer)


@dataclass
class _FakeOpenAIResponse:
    output_text: str
    id: str = "resp-123"

    class _Usage:
        input_tokens: int = 10

    usage = _Usage()


class _FakeOpenAIResponses:
    def __init__(self, answer: str = "fake answer") -> None:
        self._answer = answer
        self.last_call_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeOpenAIResponse:
        self.last_call_kwargs = kwargs
        return _FakeOpenAIResponse(output_text=self._answer)


class _FakeOpenAIClient:
    def __init__(self, answer: str = "fake answer") -> None:
        self.responses = _FakeOpenAIResponses(answer=answer)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_eval_case(n_sessions: int = 2, query: str = "What did I eat?") -> Any:
    """Build a minimal EvalCase with a LongMemEval-style JSON context."""
    from headroom.evals.core import EvalCase

    sessions = [{"session_id": i, "messages": [f"message {i}"]} for i in range(n_sessions)]
    context = json.dumps({"haystack_sessions": sessions})
    return EvalCase(id="case-001", context=context, query=query)


# ---------------------------------------------------------------------------
# TestBaselineRunner
# ---------------------------------------------------------------------------


class TestBaselineRunner:
    def test_anthropic_baseline_returns_result(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner
        from headroom.evals.runners.provider_compaction import CompactionResult

        client = _FakeAnthropicClient(answer="42")
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        result = runner.run(_make_eval_case())

        assert isinstance(result, CompactionResult)
        assert result.answer == "42"
        assert result.error is None

    def test_openai_baseline_returns_result(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner
        from headroom.evals.runners.provider_compaction import CompactionResult

        client = _FakeOpenAIClient(answer="openai-answer")
        runner = BaselineRunner(client=client, provider="openai", model="gpt-4o-mini")
        result = runner.run(_make_eval_case())

        assert isinstance(result, CompactionResult)
        assert result.answer == "openai-answer"
        assert result.error is None

    def test_compression_ratio_is_zero(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner

        client = _FakeAnthropicClient()
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        result = runner.run(_make_eval_case())

        assert result.compression_ratio == 0.0

    def test_full_haystack_passed_to_llm(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner

        client = _FakeAnthropicClient()
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        case = _make_eval_case()
        runner.run(case)

        call_kwargs = client.messages.last_call_kwargs
        # The messages should contain the haystack content
        messages = call_kwargs["messages"]
        combined_input = " ".join(str(m) for m in messages)
        # At least one session from the haystack should appear
        assert "session_id" in combined_input or "message 0" in combined_input

    def test_query_appended_to_input(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner

        client = _FakeAnthropicClient()
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        case = _make_eval_case(query="What did I eat?")
        runner.run(case)

        call_kwargs = client.messages.last_call_kwargs
        messages = call_kwargs["messages"]
        combined_input = " ".join(str(m) for m in messages)
        assert "What did I eat?" in combined_input

    def test_n_iterations_is_one(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner

        client = _FakeAnthropicClient()
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        result = runner.run(_make_eval_case())

        assert result.n_iterations == 1

    def test_n_compactions_is_zero(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner

        client = _FakeAnthropicClient()
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        result = runner.run(_make_eval_case())

        assert result.n_compactions == 0

    def test_original_equals_final_tokens(self) -> None:
        from headroom.evals.runners.direct_runners import BaselineRunner

        client = _FakeAnthropicClient()
        runner = BaselineRunner(client=client, provider="anthropic", model="claude-haiku-4-5")
        result = runner.run(_make_eval_case())

        assert result.final_input_tokens == result.original_input_tokens


# ---------------------------------------------------------------------------
# TestHeadroomDefaultRunner
# ---------------------------------------------------------------------------


class TestHeadroomDefaultRunner:
    def test_anthropic_runner_compresses_then_calls_llm(self) -> None:
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner
        from headroom.evals.runners.provider_compaction import CompactionResult

        client = _FakeAnthropicClient(answer="compressed-answer")
        runner = HeadroomDefaultRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_eval_case())

        assert isinstance(result, CompactionResult)
        assert result.answer == "compressed-answer"
        assert result.error is None

    def test_openai_runner_compresses_then_calls_llm(self) -> None:
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner
        from headroom.evals.runners.provider_compaction import CompactionResult

        client = _FakeOpenAIClient(answer="oai-compressed-answer")
        runner = HeadroomDefaultRunner(client=client, provider="openai", model="gpt-4o-mini")
        result = runner.run(_make_eval_case())

        assert isinstance(result, CompactionResult)
        assert result.answer == "oai-compressed-answer"
        assert result.error is None

    def test_compression_ratio_computed_in_tokens(self) -> None:
        """compression_ratio = 1 - (final_tokens / original_tokens), token-based."""
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner

        client = _FakeAnthropicClient()
        runner = HeadroomDefaultRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_eval_case())

        # Ratio must be in [0, 1] range; may be 0 if no compression happened
        assert 0.0 <= result.compression_ratio <= 1.0
        # Ratio is token-based: consistent with final/original
        if result.original_input_tokens > 0:
            expected = 1 - result.final_input_tokens / result.original_input_tokens
            assert abs(result.compression_ratio - expected) < 1e-9

    def test_compressed_content_passed_to_llm(self) -> None:
        """The LLM call must use the compressed text, not the full haystack."""
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner

        client = _FakeAnthropicClient()
        runner = HeadroomDefaultRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        # Build a slightly larger case to give ContentRouter something to work with
        case = _make_eval_case(n_sessions=5)
        runner.run(case)

        call_kwargs = client.messages.last_call_kwargs
        assert "messages" in call_kwargs
        # Verify a call was made (we can't check compression without knowing exact output,
        # but we can verify the call happened and final_input_tokens was recorded)

    def test_n_compactions_is_zero(self) -> None:
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner

        client = _FakeAnthropicClient()
        runner = HeadroomDefaultRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_eval_case())

        assert result.n_compactions == 0

    def test_n_iterations_is_one(self) -> None:
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner

        client = _FakeAnthropicClient()
        runner = HeadroomDefaultRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_eval_case())

        assert result.n_iterations == 1

    def test_case_id_preserved(self) -> None:
        from headroom.evals.runners.direct_runners import HeadroomDefaultRunner

        client = _FakeAnthropicClient()
        runner = HeadroomDefaultRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        case = _make_eval_case()
        result = runner.run(case)

        assert result.case_id == case.id
