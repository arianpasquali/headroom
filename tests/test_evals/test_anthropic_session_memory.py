"""Tests for AnthropicSessionMemoryRunner (cookbook pattern)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _FakeText:
    text: str


@dataclass
class _FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _FakeResponse:
    content: list[_FakeText]
    usage: _FakeUsage


class _ScriptedMessages:
    """Returns a scripted sequence of responses: [summary_response, answer_response]."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self._calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self._calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("no more scripted responses")
        return self._responses.pop(0)

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return self._calls


@dataclass
class _FakeClient:
    messages: _ScriptedMessages


def _make_case(query: str = "What did the user say?") -> Any:
    from headroom.evals.core import EvalCase

    sessions = [{"session_id": i, "messages": [f"m{i}"]} for i in range(3)]
    return EvalCase(
        id="case-session-memory",
        context=json.dumps({"haystack_sessions": sessions}),
        query=query,
    )


def _mk_response(text: str, input_tokens: int = 0, output_tokens: int = 0) -> _FakeResponse:
    return _FakeResponse(
        content=[_FakeText(text=text)],
        usage=_FakeUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class TestAnthropicSessionMemoryRunner:
    def test_makes_two_calls_summary_then_answer(self) -> None:
        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        msgs = _ScriptedMessages([
            _mk_response("<session_memory>the user graduated with Biology</session_memory>"),
            _mk_response("According to our prior conversation, you graduated with Biology."),
        ])
        client = _FakeClient(messages=msgs)
        runner = AnthropicSessionMemoryRunner(client=client)
        result = runner.run(_make_case())

        assert len(msgs.call_log) == 2
        assert result.n_iterations == 2
        assert result.n_compactions == 1
        assert "Biology" in result.answer
        assert result.error is None

    def test_summary_call_uses_summary_model(self) -> None:
        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        msgs = _ScriptedMessages([
            _mk_response("<session_memory>...</session_memory>"),
            _mk_response("the answer"),
        ])
        client = _FakeClient(messages=msgs)
        runner = AnthropicSessionMemoryRunner(
            client=client,
            answer_model="claude-sonnet-4-6",
            summary_model="claude-haiku-4-5-20251001",
        )
        runner.run(_make_case())

        assert msgs.call_log[0]["model"] == "claude-haiku-4-5-20251001"
        assert msgs.call_log[1]["model"] == "claude-sonnet-4-6"

    def test_summary_call_uses_cache_control(self) -> None:
        """Cache control is passed even though it won't hit in one-shot eval."""
        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        msgs = _ScriptedMessages([
            _mk_response("<session_memory>...</session_memory>"),
            _mk_response("the answer"),
        ])
        client = _FakeClient(messages=msgs)
        runner = AnthropicSessionMemoryRunner(client=client)
        runner.run(_make_case())

        summary_call = msgs.call_log[0]
        # System is a list of blocks with cache_control on the prompt.
        sys_blocks = summary_call["system"]
        assert any(b.get("cache_control") == {"type": "ephemeral"} for b in sys_blocks)
        # User message content list has cache_control on the haystack block.
        user_msg = summary_call["messages"][0]
        user_blocks = user_msg["content"]
        assert any(b.get("cache_control") == {"type": "ephemeral"} for b in user_blocks)

    def test_answer_call_sees_summary_and_question_only(self) -> None:
        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        msgs = _ScriptedMessages([
            _mk_response("<session_memory>the user said X</session_memory>"),
            _mk_response("X"),
        ])
        client = _FakeClient(messages=msgs)
        runner = AnthropicSessionMemoryRunner(client=client)
        runner.run(_make_case(query="What did the user say?"))

        answer_call = msgs.call_log[1]
        answer_content = answer_call["messages"][0]["content"]
        assert "session_memory" in answer_content
        assert "What did the user say?" in answer_content
        # Answer call must NOT see the raw haystack.
        assert '"session_id"' not in answer_content

    def test_user_visible_latency_excludes_summary(self) -> None:
        """user_visible_latency_ms must be ≤ wall-clock (summary is excluded)."""
        import time as _time

        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        class _SlowSummaryMessages(_ScriptedMessages):
            def create(self, **kwargs: Any) -> _FakeResponse:
                # Sleep on the summary call only (first call).
                if len(self._calls) == 0:
                    _time.sleep(0.05)
                return super().create(**kwargs)

        msgs = _SlowSummaryMessages([
            _mk_response("<session_memory>...</session_memory>"),
            _mk_response("the answer"),
        ])
        client = _FakeClient(messages=msgs)
        runner = AnthropicSessionMemoryRunner(client=client)
        result = runner.run(_make_case())

        # wall-clock should be > user_visible because the summary took 50ms.
        assert result.latency_ms > result.user_visible_latency_ms
        assert result.user_visible_latency_ms < result.latency_ms  # clearly separated

    def test_cost_sums_summary_and_answer(self) -> None:
        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        msgs = _ScriptedMessages([
            _mk_response(
                "<session_memory>...</session_memory>",
                input_tokens=100_000,
                output_tokens=500,
            ),
            _mk_response("the answer", input_tokens=1000, output_tokens=50),
        ])
        client = _FakeClient(messages=msgs)
        runner = AnthropicSessionMemoryRunner(
            client=client,
            answer_model="claude-sonnet-4-6",
            summary_model="claude-haiku-4-5-20251001",
        )
        result = runner.run(_make_case())

        # Haiku 4.5 pricing: $0.80/M input, $4/M output.
        # Summary:  100000 * 0.80/1e6 + 500 * 4/1e6 = 0.080 + 0.002 = 0.082
        # Sonnet 4.6 pricing: $3/M input, $15/M output.
        # Answer:   1000 * 3/1e6 + 50 * 15/1e6 = 0.003 + 0.00075 = 0.00375
        # Total:                                                 = 0.08575
        assert abs(result.cost_usd - 0.08575) < 1e-4

    def test_summary_failure_returns_error_result(self) -> None:
        from headroom.evals.runners.anthropic_session_memory import AnthropicSessionMemoryRunner

        class _RaisingSummary:
            def create(self, **kwargs: Any) -> Any:
                raise RuntimeError("summary boom")

        client = _FakeClient(messages=_RaisingSummary())
        runner = AnthropicSessionMemoryRunner(client=client)
        result = runner.run(_make_case())

        assert result.error is not None
        assert "summary" in result.error.lower()
        assert result.answer == ""
