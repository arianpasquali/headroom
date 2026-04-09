"""Tests for the floor-test runners (DumbTruncationLastN, RandomChunkDrop)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Fake clients — reused shape from test_direct_runners.py
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


class _RaisingAnthropicClient:
    class _RaisingMessages:
        last_call_kwargs: dict[str, Any] = {}

        def create(self, **kwargs: Any) -> Any:
            self.last_call_kwargs = kwargs
            raise RuntimeError("kaboom")

    def __init__(self) -> None:
        self.messages = _RaisingAnthropicClient._RaisingMessages()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_long_case(query: str = "What did I say?") -> Any:
    """EvalCase with a bigger haystack so truncation/drop actually produces a
    measurable compression ratio on a tiktoken-level basis."""
    from headroom.evals.core import EvalCase

    # Each session has ~60 tokens of text; 40 sessions gives ~2400 tokens.
    sessions = [
        {
            "session_id": i,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Session {i}: some filler text about ordinary things, like food, "
                        f"weather, and plans for the weekend. A very specific fact: marker_{i}."
                    ),
                }
            ],
        }
        for i in range(40)
    ]
    context = json.dumps({"haystack_sessions": sessions})
    return EvalCase(id=f"case-long-{query[:10]}", context=context, query=query)


# ---------------------------------------------------------------------------
# DumbTruncationLastNRunner
# ---------------------------------------------------------------------------


class TestDumbTruncationLastNRunner:
    def test_returns_compaction_result(self) -> None:
        from headroom.evals.runners.floor_tests import DumbTruncationLastNRunner
        from headroom.evals.runners.provider_compaction import CompactionResult

        client = _FakeAnthropicClient(answer="answer")
        runner = DumbTruncationLastNRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_long_case())

        assert isinstance(result, CompactionResult)
        assert result.answer == "answer"
        assert result.error is None
        assert result.n_iterations == 1
        assert result.n_compactions == 0

    def test_compression_ratio_is_near_target(self) -> None:
        from headroom.evals.runners.floor_tests import DumbTruncationLastNRunner

        client = _FakeAnthropicClient()
        runner = DumbTruncationLastNRunner(
            client=client,
            provider="anthropic",
            model="claude-haiku-4-5",
            target_compression_ratio=0.54,
        )
        result = runner.run(_make_long_case())

        # Allow ±2% slop from rounding at token boundaries.
        assert 0.52 <= result.compression_ratio <= 0.56, (
            f"compression_ratio={result.compression_ratio} should be near 0.54"
        )

    def test_target_ratio_zero_passes_through(self) -> None:
        """target=0.0 → keep everything → compression_ratio = 0.0"""
        from headroom.evals.runners.floor_tests import DumbTruncationLastNRunner

        client = _FakeAnthropicClient()
        runner = DumbTruncationLastNRunner(
            client=client,
            provider="anthropic",
            model="claude-haiku-4-5",
            target_compression_ratio=0.0,
        )
        result = runner.run(_make_long_case())

        assert result.compression_ratio == 0.0
        assert result.final_input_tokens == result.original_input_tokens

    def test_keeps_last_tokens_not_first(self) -> None:
        """Dumb truncation keeps the *end* of the haystack. The last session
        marker should survive; the first should be gone."""
        from headroom.evals.runners.floor_tests import DumbTruncationLastNRunner

        client = _FakeAnthropicClient()
        runner = DumbTruncationLastNRunner(
            client=client,
            provider="anthropic",
            model="claude-haiku-4-5",
            target_compression_ratio=0.80,  # keep only 20% — should lose early sessions
        )
        runner.run(_make_long_case())

        last_call = client.messages.last_call_kwargs
        input_text = last_call["messages"][0]["content"]
        # Late marker should survive; early marker should be dropped.
        assert "marker_39" in input_text
        assert "marker_0" not in input_text

    def test_query_appended_to_input(self) -> None:
        from headroom.evals.runners.floor_tests import DumbTruncationLastNRunner

        client = _FakeAnthropicClient()
        runner = DumbTruncationLastNRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        case = _make_long_case(query="unique question marker")
        runner.run(case)

        input_text = client.messages.last_call_kwargs["messages"][0]["content"]
        assert "unique question marker" in input_text

    def test_error_returns_error_result(self) -> None:
        from headroom.evals.runners.floor_tests import DumbTruncationLastNRunner

        client = _RaisingAnthropicClient()
        runner = DumbTruncationLastNRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_long_case())

        assert result.error is not None
        assert "kaboom" in result.error
        assert result.answer == ""


# ---------------------------------------------------------------------------
# RandomChunkDropRunner
# ---------------------------------------------------------------------------


class TestRandomChunkDropRunner:
    def test_returns_compaction_result(self) -> None:
        from headroom.evals.runners.floor_tests import RandomChunkDropRunner
        from headroom.evals.runners.provider_compaction import CompactionResult

        client = _FakeAnthropicClient(answer="answer")
        runner = RandomChunkDropRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_long_case())

        assert isinstance(result, CompactionResult)
        assert result.answer == "answer"
        assert result.error is None
        assert result.n_iterations == 1
        assert result.n_compactions == 0

    def test_compression_ratio_is_near_target(self) -> None:
        from headroom.evals.runners.floor_tests import RandomChunkDropRunner

        client = _FakeAnthropicClient()
        runner = RandomChunkDropRunner(
            client=client,
            provider="anthropic",
            model="claude-haiku-4-5",
            target_compression_ratio=0.54,
            chunk_token_size=200,
        )
        result = runner.run(_make_long_case())

        # Random chunk drop lands close-but-not-exact because chunks are
        # a discrete quantity. Allow generous tolerance.
        assert 0.45 <= result.compression_ratio <= 0.65, (
            f"compression_ratio={result.compression_ratio} should be near 0.54"
        )

    def test_deterministic_per_case(self) -> None:
        """Two runs of the same case produce identical compressed output."""
        from headroom.evals.runners.floor_tests import RandomChunkDropRunner

        client_a = _FakeAnthropicClient()
        client_b = _FakeAnthropicClient()
        runner_a = RandomChunkDropRunner(
            client=client_a,
            provider="anthropic",
            model="claude-haiku-4-5",
            chunk_token_size=200,
        )
        runner_b = RandomChunkDropRunner(
            client=client_b,
            provider="anthropic",
            model="claude-haiku-4-5",
            chunk_token_size=200,
        )
        case = _make_long_case()
        runner_a.run(case)
        runner_b.run(case)

        input_a = client_a.messages.last_call_kwargs["messages"][0]["content"]
        input_b = client_b.messages.last_call_kwargs["messages"][0]["content"]
        assert input_a == input_b

    def test_different_cases_drop_different_chunks(self) -> None:
        """Two different case ids should use different random seeds and drop
        different chunks, so the compressed outputs differ."""
        from headroom.evals.core import EvalCase
        from headroom.evals.runners.floor_tests import RandomChunkDropRunner

        sessions = [
            {"session_id": i, "messages": [{"role": "user", "content": f"marker_{i} " * 30}]}
            for i in range(30)
        ]
        ctx = json.dumps({"haystack_sessions": sessions})

        case_a = EvalCase(id="case-alpha", context=ctx, query="q")
        case_b = EvalCase(id="case-beta", context=ctx, query="q")

        client_a = _FakeAnthropicClient()
        client_b = _FakeAnthropicClient()
        runner_a = RandomChunkDropRunner(
            client=client_a,
            provider="anthropic",
            model="claude-haiku-4-5",
            chunk_token_size=200,
        )
        runner_b = RandomChunkDropRunner(
            client=client_b,
            provider="anthropic",
            model="claude-haiku-4-5",
            chunk_token_size=200,
        )
        runner_a.run(case_a)
        runner_b.run(case_b)

        input_a = client_a.messages.last_call_kwargs["messages"][0]["content"]
        input_b = client_b.messages.last_call_kwargs["messages"][0]["content"]
        assert input_a != input_b

    def test_query_appended_to_input(self) -> None:
        from headroom.evals.runners.floor_tests import RandomChunkDropRunner

        client = _FakeAnthropicClient()
        runner = RandomChunkDropRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        case = _make_long_case(query="unique question marker")
        runner.run(case)

        input_text = client.messages.last_call_kwargs["messages"][0]["content"]
        assert "unique question marker" in input_text

    def test_error_returns_error_result(self) -> None:
        from headroom.evals.runners.floor_tests import RandomChunkDropRunner

        client = _RaisingAnthropicClient()
        runner = RandomChunkDropRunner(
            client=client, provider="anthropic", model="claude-haiku-4-5"
        )
        result = runner.run(_make_long_case())

        assert result.error is not None
        assert "kaboom" in result.error
        assert result.answer == ""
