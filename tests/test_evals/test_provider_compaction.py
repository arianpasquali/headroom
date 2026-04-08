"""Tests for provider_compaction runners (Anthropic + OpenAI).

All tests use fake/stub clients — no real API calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from headroom.evals.core import EvalCase
from headroom.evals.runners.provider_compaction import (
    AnthropicCompactionRunner,
    CompactionResult,
    OpenAICompactionRunner,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_FAKE_SESSIONS = [
    {"role": "user", "content": "What is the capital of France?"},
    {"role": "assistant", "content": "The capital of France is Paris."},
    {"role": "user", "content": "What year was the Eiffel Tower built?"},
    {"role": "assistant", "content": "The Eiffel Tower was built in 1889."},
]

_FAKE_CONTEXT = json.dumps(
    {
        "haystack_sessions": _FAKE_SESSIONS,
        "haystack_dates": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
    }
)

_FAKE_CASE = EvalCase(
    id="test-case-1",
    context=_FAKE_CONTEXT,
    query="When was the Eiffel Tower built?",
    ground_truth="1889",
)


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _FakeToolUseBlock:
    type: str = "tool_use"
    id: str = "tu_1"
    name: str = "read_history"
    input: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.input is None:
            self.input = {"chunk_id": 0}


@dataclass
class _FakeTextBlock:
    type: str = "text"
    text: str = "done"


@dataclass
class _FakeBetaMessage:
    role: str = "assistant"
    stop_reason: str = "tool_use"
    usage: _FakeUsage = None  # type: ignore[assignment]
    content: list = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.usage is None:
            self.usage = _FakeUsage(input_tokens=100, output_tokens=20)
        if self.content is None:
            self.content = [_FakeToolUseBlock()]


class _FakeToolRunner:
    """Fake BetaToolRunner that calls the injected tools and yields messages."""

    def __init__(self, messages_to_yield: list[_FakeBetaMessage], tools_by_name: dict):
        self._messages = messages_to_yield
        self._tools_by_name = tools_by_name
        self._called_with: dict[str, Any] = {}

    def __iter__(self):
        for msg in self._messages:
            # Execute any tool calls so side effects (submit_answer) fire
            for block in msg.content:
                if block.type == "tool_use":
                    tool = self._tools_by_name.get(block.name)
                    if tool is not None:
                        tool.call(block.input)
            yield msg

    def until_done(self):
        for _ in self:
            pass
        return self._messages[-1]


class _FakeAnthropicClient:
    """Stub that mimics client.beta.messages.tool_runner."""

    def __init__(self, messages_to_yield: list[_FakeBetaMessage] | None = None):
        self._messages_to_yield = messages_to_yield or [
            _FakeBetaMessage(
                stop_reason="tool_use",
                usage=_FakeUsage(input_tokens=200, output_tokens=30),
                content=[_FakeToolUseBlock(name="read_history", input={"chunk_id": 0})],
            ),
            _FakeBetaMessage(
                stop_reason="tool_use",
                usage=_FakeUsage(input_tokens=50, output_tokens=20),  # drop = compaction
                content=[_FakeToolUseBlock(name="submit_answer", input={"answer": "1889"})],
            ),
            _FakeBetaMessage(
                stop_reason="end_turn",
                usage=_FakeUsage(input_tokens=60, output_tokens=10),
                content=[_FakeTextBlock()],
            ),
        ]
        self.last_tool_runner_kwargs: dict[str, Any] = {}
        self.beta = self

        class _Messages:
            def __init__(inner_self):
                pass

            def tool_runner(inner_self, **kwargs):
                self.last_tool_runner_kwargs = kwargs
                # Extract tool callables so the fake runner can invoke them
                tools_by_name: dict = {}
                for t in kwargs.get("tools", []):
                    # BetaFunctionTool wraps function; .call() invokes it
                    if hasattr(t, "name") and hasattr(t, "call"):
                        tools_by_name[t.name] = t
                return _FakeToolRunner(self._messages_to_yield, tools_by_name)

        self.messages = _Messages()


# ---------------------------------------------------------------------------
# Fake OpenAI client
# ---------------------------------------------------------------------------


@dataclass
class _FakeOAIUsage:
    input_tokens: int = 100
    output_tokens: int = 20


@dataclass
class _FakeOAIResponse:
    id: str = "resp_001"
    output_text: str = ""
    usage: _FakeOAIUsage = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.usage is None:
            self.usage = _FakeOAIUsage()


class _FakeOAIResponses:
    def __init__(
        self, responses: list[_FakeOAIResponse], compact_response: _FakeOAIResponse | None = None
    ):
        self._responses = list(responses)
        self._compact_response = compact_response or _FakeOAIResponse(id="compacted_001")
        self._create_calls: list[dict] = []
        self._compact_calls: list[dict] = []

    def create(self, **kwargs) -> _FakeOAIResponse:
        self._create_calls.append(kwargs)
        if self._responses:
            return self._responses.pop(0)
        return _FakeOAIResponse(id="resp_final", output_text="1889")

    def compact(self, **kwargs) -> _FakeOAIResponse:
        self._compact_calls.append(kwargs)
        return self._compact_response


class _FakeOpenAIClient:
    """Stub that mimics client.responses.create + compact."""

    def __init__(
        self,
        responses: list[_FakeOAIResponse] | None = None,
        compact_response: _FakeOAIResponse | None = None,
    ):
        _responses = responses or [
            _FakeOAIResponse(id="resp_001", output_text="", usage=_FakeOAIUsage(input_tokens=200)),
            _FakeOAIResponse(
                id="resp_002", output_text="1889", usage=_FakeOAIUsage(input_tokens=30)
            ),
        ]
        self.responses = _FakeOAIResponses(_responses, compact_response)


class _FakeOpenAIClientNoCompact:
    """OpenAI client stub that has no compact method (simulates old SDK)."""

    def __init__(self):
        self.responses = _NoCompactResponses()


class _NoCompactResponses:
    def create(self, **kwargs):
        return _FakeOAIResponse()

    # compact intentionally absent


# ---------------------------------------------------------------------------
# Tests: AnthropicCompactionRunner
# ---------------------------------------------------------------------------


class TestAnthropicCompactionRunner:
    def _make_runner(self, client=None, **kwargs) -> AnthropicCompactionRunner:
        if client is None:
            client = _FakeAnthropicClient()
        return AnthropicCompactionRunner(client=client, **kwargs)

    def test_returns_compaction_result_with_answer(self):
        runner = self._make_runner()
        result = runner.run(_FAKE_CASE)
        assert isinstance(result, CompactionResult)
        assert result.case_id == "test-case-1"
        assert result.answer == "1889"
        assert result.error is None

    def test_compression_ratio_calculated_correctly(self):
        runner = self._make_runner()
        result = runner.run(_FAKE_CASE)
        # original_input_tokens > 0; final_input_tokens = sum of per-iteration counts
        assert result.original_input_tokens > 0
        assert result.final_input_tokens > 0
        expected_ratio = 1 - (result.final_input_tokens / result.original_input_tokens)
        assert abs(result.compression_ratio - expected_ratio) < 1e-6

    def test_latency_recorded_in_ms(self):
        runner = self._make_runner()
        result = runner.run(_FAKE_CASE)
        assert result.latency_ms >= 0
        # Should be a plausible wall-clock value (not zero or astronomical)
        assert result.latency_ms < 60_000  # under 1 minute

    def test_chunks_haystack_into_chunk_token_size_pieces(self):
        # Use a very small chunk size so we get multiple chunks
        runner = self._make_runner(chunk_token_size=5)
        runner.run(_FAKE_CASE)
        # The runner should have computed at least 2 chunks
        assert len(runner._chunks) >= 2

    def test_passes_compaction_control_to_tool_runner(self):
        fake_client = _FakeAnthropicClient()
        runner = AnthropicCompactionRunner(
            client=fake_client,
            context_token_threshold=12345,
        )
        runner.run(_FAKE_CASE)
        kwargs = fake_client.last_tool_runner_kwargs
        cc = kwargs.get("compaction_control", {})
        assert cc.get("enabled") is True
        assert cc.get("context_token_threshold") == 12345

    def test_counts_compaction_events_from_token_drops(self):
        # Messages: 200 tokens, then 50 (drop => compaction), then 60
        fake_client = _FakeAnthropicClient()
        runner = AnthropicCompactionRunner(client=fake_client)
        result = runner.run(_FAKE_CASE)
        # The token drop from 200 to 50 should register as one compaction event
        assert result.n_compactions >= 1

    def test_n_iterations_tracked(self):
        fake_client = _FakeAnthropicClient()
        runner = AnthropicCompactionRunner(client=fake_client)
        result = runner.run(_FAKE_CASE)
        # Runner stops as soon as submit_answer fires (after 2nd message),
        # so we expect 2 iterations (not 3).
        assert result.n_iterations == 2


# ---------------------------------------------------------------------------
# Tests: OpenAICompactionRunner
# ---------------------------------------------------------------------------


class TestOpenAICompactionRunner:
    def _make_runner(self, client=None, **kwargs) -> OpenAICompactionRunner:
        if client is None:
            client = _FakeOpenAIClient()
        return OpenAICompactionRunner(client=client, **kwargs)

    def test_returns_compaction_result_with_answer(self):
        # Provide enough responses: one per chunk + one final
        fake_client = _FakeOpenAIClient(
            responses=[
                _FakeOAIResponse(id="r1", output_text="", usage=_FakeOAIUsage(input_tokens=100)),
                _FakeOAIResponse(id="r2", output_text="1889", usage=_FakeOAIUsage(input_tokens=80)),
            ]
        )
        runner = self._make_runner(client=fake_client)
        result = runner.run(_FAKE_CASE)
        assert isinstance(result, CompactionResult)
        assert result.case_id == "test-case-1"
        assert result.answer == "1889"
        assert result.error is None

    def test_compression_ratio_calculated_correctly(self):
        fake_client = _FakeOpenAIClient(
            responses=[
                _FakeOAIResponse(id="r1", output_text="", usage=_FakeOAIUsage(input_tokens=300)),
                _FakeOAIResponse(id="r2", output_text="1889", usage=_FakeOAIUsage(input_tokens=50)),
            ]
        )
        runner = self._make_runner(client=fake_client)
        result = runner.run(_FAKE_CASE)
        assert result.original_input_tokens > 0
        assert result.final_input_tokens > 0
        expected = 1 - (result.final_input_tokens / result.original_input_tokens)
        assert abs(result.compression_ratio - expected) < 1e-6

    def test_passes_compact_threshold_through(self):
        # Set a very low threshold so compaction fires
        fake_client = _FakeOpenAIClient(
            responses=[
                _FakeOAIResponse(id="r1", output_text="", usage=_FakeOAIUsage(input_tokens=200)),
                _FakeOAIResponse(id="r2", output_text="1889", usage=_FakeOAIUsage(input_tokens=80)),
            ],
            compact_response=_FakeOAIResponse(
                id="compacted", output_text="", usage=_FakeOAIUsage(input_tokens=10)
            ),
        )
        runner = OpenAICompactionRunner(client=fake_client, compact_threshold=1)
        result = runner.run(_FAKE_CASE)
        # With threshold=1, at least one compact call should have fired
        assert result.n_compactions >= 1
        assert len(fake_client.responses._compact_calls) >= 1

    def test_handles_missing_compact_endpoint_gracefully(self):
        client_no_compact = _FakeOpenAIClientNoCompact()
        with pytest.raises(NotImplementedError, match="compaction unavailable"):
            OpenAICompactionRunner(client=client_no_compact)
