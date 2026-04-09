"""Tests for AnthropicCompactV2Runner (server-side compact_20260112)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeCompactionBlock:
    content: str
    type: str = "compaction"


@dataclass
class _FakeIter:
    type: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    iterations: list[_FakeIter] = field(default_factory=list)


@dataclass
class _FakeBetaResponse:
    content: list[Any]
    usage: _FakeUsage


class _FakeBetaMessages:
    """Captures calls and returns a canned response with compaction + text."""

    def __init__(
        self,
        compaction_summary: str = "The user mentioned X.",
        answer: str = "According to our prior conversation, X.",
        input_tokens: int = 125_000,
        compaction_out_tokens: int = 120,
        answer_in_tokens: int = 350,
        answer_out_tokens: int = 40,
    ) -> None:
        self.compaction_summary = compaction_summary
        self.answer = answer
        self.input_tokens = input_tokens
        self.compaction_out_tokens = compaction_out_tokens
        self.answer_in_tokens = answer_in_tokens
        self.answer_out_tokens = answer_out_tokens
        self.last_call_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeBetaResponse:
        self.last_call_kwargs = kwargs
        iters = [
            _FakeIter(
                type="compaction",
                input_tokens=self.input_tokens,
                output_tokens=self.compaction_out_tokens,
            ),
            _FakeIter(
                type="message",
                input_tokens=self.answer_in_tokens,
                output_tokens=self.answer_out_tokens,
            ),
        ]
        content = [
            _FakeCompactionBlock(content=self.compaction_summary),
            _FakeTextBlock(text=self.answer),
        ]
        usage = _FakeUsage(
            input_tokens=self.answer_in_tokens,
            output_tokens=self.answer_out_tokens,
            iterations=iters,
        )
        return _FakeBetaResponse(content=content, usage=usage)


class _FakeBetaClient:
    """Mirrors `client.beta.messages.create(...)`."""

    def __init__(self, messages: _FakeBetaMessages) -> None:
        self.beta = _FakeBeta(messages=messages)


@dataclass
class _FakeBeta:
    messages: _FakeBetaMessages


def _make_case(query: str = "What did I say?") -> Any:
    from headroom.evals.core import EvalCase

    sessions = [{"session_id": i, "messages": [f"m{i}"]} for i in range(3)]
    return EvalCase(
        id="case-v2",
        context=json.dumps({"haystack_sessions": sessions}),
        query=query,
    )


class TestAnthropicCompactV2Runner:
    def test_returns_compaction_result_with_expected_answer(self) -> None:
        from headroom.evals.runners.anthropic_compact_v2 import AnthropicCompactV2Runner
        from headroom.evals.runners.provider_compaction import CompactionResult

        fake_msgs = _FakeBetaMessages(
            compaction_summary="The user graduated with a degree in Biology.",
            answer="According to our prior conversation, you graduated with Biology.",
        )
        client = _FakeBetaClient(messages=fake_msgs)
        runner = AnthropicCompactV2Runner(client=client, model="claude-sonnet-4-6")
        result = runner.run(_make_case())

        assert isinstance(result, CompactionResult)
        assert "Biology" in result.answer
        assert result.error is None
        assert result.n_compactions == 1
        assert result.n_iterations == 2

    def test_compression_ratio_computed_from_message_iter(self) -> None:
        from headroom.evals.runners.anthropic_compact_v2 import AnthropicCompactV2Runner

        fake_msgs = _FakeBetaMessages(input_tokens=100_000, answer_in_tokens=500)
        client = _FakeBetaClient(messages=fake_msgs)
        runner = AnthropicCompactV2Runner(client=client, model="claude-sonnet-4-6")
        result = runner.run(_make_case())

        # final_input_tokens should be 500 (the message iteration input);
        # compression_ratio = 1 - 500/original, where original is whatever
        # tiktoken computes on the tiny flattened haystack (a small number).
        # We just assert the final_input_tokens is read from the iteration.
        assert result.final_input_tokens == 500

    def test_passes_beta_header_and_context_management(self) -> None:
        from headroom.evals.runners.anthropic_compact_v2 import (
            AnthropicCompactV2Runner,
            BETA_HEADER,
            DEFAULT_COMPACTION_INSTRUCTIONS,
        )

        fake_msgs = _FakeBetaMessages()
        client = _FakeBetaClient(messages=fake_msgs)
        runner = AnthropicCompactV2Runner(
            client=client,
            model="claude-sonnet-4-6",
            trigger_input_tokens=55_000,
        )
        runner.run(_make_case())

        kwargs = fake_msgs.last_call_kwargs
        assert kwargs["betas"] == [BETA_HEADER]
        assert kwargs["model"] == "claude-sonnet-4-6"

        edits = kwargs["context_management"]["edits"]
        assert len(edits) == 1
        edit = edits[0]
        assert edit["type"] == "compact_20260112"
        assert edit["trigger"] == {"type": "input_tokens", "value": 55_000}
        assert edit["instructions"] == DEFAULT_COMPACTION_INSTRUCTIONS

    def test_custom_compaction_instructions_are_passed_through(self) -> None:
        from headroom.evals.runners.anthropic_compact_v2 import AnthropicCompactV2Runner

        fake_msgs = _FakeBetaMessages()
        client = _FakeBetaClient(messages=fake_msgs)
        runner = AnthropicCompactV2Runner(
            client=client,
            compaction_instructions="Custom instructions.",
        )
        runner.run(_make_case())

        edit = fake_msgs.last_call_kwargs["context_management"]["edits"][0]
        assert edit["instructions"] == "Custom instructions."

    def test_system_prompt_disambiguates_roles(self) -> None:
        """The default system prompt must tell the model that compaction
        block 'you' refers to the user, not to the assistant."""
        from headroom.evals.runners.anthropic_compact_v2 import DEFAULT_SYSTEM_PROMPT

        assert "user" in DEFAULT_SYSTEM_PROMPT.lower()
        assert "not describing you" in DEFAULT_SYSTEM_PROMPT.lower() or "refers to the user" in DEFAULT_SYSTEM_PROMPT.lower()

    def test_cost_is_computed_from_iterations(self) -> None:
        from headroom.evals.runners.anthropic_compact_v2 import AnthropicCompactV2Runner

        fake_msgs = _FakeBetaMessages(
            input_tokens=100_000,
            compaction_out_tokens=200,
            answer_in_tokens=500,
            answer_out_tokens=50,
        )
        client = _FakeBetaClient(messages=fake_msgs)
        runner = AnthropicCompactV2Runner(client=client, model="claude-sonnet-4-6")
        result = runner.run(_make_case())

        # Sonnet 4.6 pricing: $3/M input, $15/M output.
        # compaction iter: 100000 * 3/1e6 + 200 * 15/1e6 = 0.300 + 0.003 = 0.303
        # message iter:    500 * 3/1e6  +  50 * 15/1e6 = 0.0015 + 0.00075 = 0.00225
        # total:                                          = 0.30525
        assert abs(result.cost_usd - 0.30525) < 1e-4

    def test_error_returns_result_with_error_field(self) -> None:
        from headroom.evals.runners.anthropic_compact_v2 import AnthropicCompactV2Runner

        class _RaisingMessages:
            last_call_kwargs: dict[str, Any] = {}

            def create(self, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

        class _RaisingClient:
            def __init__(self) -> None:
                self.beta = _RaisingBeta()

        @dataclass
        class _RaisingBeta:
            messages: _RaisingMessages = field(default_factory=_RaisingMessages)

        runner = AnthropicCompactV2Runner(client=_RaisingClient())
        result = runner.run(_make_case())

        assert result.error is not None
        assert "boom" in result.error
        assert result.answer == ""
