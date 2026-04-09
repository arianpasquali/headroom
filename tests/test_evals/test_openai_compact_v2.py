"""Tests for OpenAICompactV2Runner (Responses API server-side compaction)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fakes — mirror the shape of openai.resources.responses.Response
# ---------------------------------------------------------------------------


@dataclass
class _FakeCompactionItem:
    """Stand-in for a Responses API compaction output item.

    The exact type label used by the real Responses API is not yet publicly
    documented; the runner checks for `type == "compaction"`, which is our
    canonical guess based on the guide language. If a real probe reveals a
    different name, update the runner AND this fake together.
    """

    type: str = "compaction"


@dataclass
class _FakeTextOutputItem:
    text: str
    type: str = "message"


@dataclass
class _FakeResponseUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    usage: _FakeResponseUsage | None = None


class _FakeResponses:
    """Captures calls and returns a canned Responses API response."""

    def __init__(
        self,
        answer: str = "According to our prior conversation, you said X.",
        input_tokens: int = 500,
        output_tokens: int = 40,
        n_compaction_items: int = 1,
    ) -> None:
        self.answer = answer
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.n_compaction_items = n_compaction_items
        self.last_call_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.last_call_kwargs = kwargs
        output: list[Any] = [_FakeCompactionItem() for _ in range(self.n_compaction_items)]
        output.append(_FakeTextOutputItem(text=self.answer))
        usage = _FakeResponseUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )
        return _FakeResponse(output_text=self.answer, output=output, usage=usage)


class _FakeOpenAIClient:
    """Mirrors `client.responses.create(...)`."""

    def __init__(self, responses: _FakeResponses) -> None:
        self.responses = responses


def _make_case(query: str = "What did I say?") -> Any:
    from headroom.evals.core import EvalCase

    sessions = [{"session_id": i, "messages": [f"m{i}"]} for i in range(3)]
    return EvalCase(
        id="case-openai-v2",
        context=json.dumps({"haystack_sessions": sessions}),
        query=query,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenAICompactV2Runner:
    def test_returns_compaction_result_with_expected_answer(self) -> None:
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner
        from headroom.evals.runners.provider_compaction import CompactionResult

        fake_responses = _FakeResponses(
            answer="According to our prior conversation, you graduated with Biology.",
        )
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(client=client, model="gpt-5.4")
        result = runner.run(_make_case())

        assert isinstance(result, CompactionResult)
        assert "Biology" in result.answer
        assert result.error is None
        assert result.n_compactions == 1
        assert result.n_iterations == 1

    def test_compression_ratio_computed_from_usage_input_tokens(self) -> None:
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses(input_tokens=500)
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(client=client, model="gpt-5.4")
        result = runner.run(_make_case())

        # final_input_tokens should be 500 (from response.usage.input_tokens);
        # compression_ratio = 1 - 500/original where original is the tiktoken
        # count of the tiny flattened haystack.
        assert result.final_input_tokens == 500

    def test_passes_context_management_via_extra_body(self) -> None:
        """`context_management` must ride in `extra_body` because the
        OpenAI Python SDK (as of 2.15.0) does not yet expose it as a
        typed parameter on `responses.create`. Passing it as a direct
        kwarg raises `got an unexpected keyword argument` from the SDK's
        Pydantic layer before the HTTP round-trip. This test pins the
        wire format so we don't silently regress if someone rewrites
        the runner to use the direct kwarg before a newer SDK lands.
        """
        from headroom.evals.runners.openai_compact_v2 import (
            DEFAULT_SYSTEM_PROMPT,
            OpenAICompactV2Runner,
        )

        fake_responses = _FakeResponses()
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(
            client=client,
            model="gpt-5.4",
            trigger_input_tokens=55_000,
            max_output_tokens=1024,
        )
        runner.run(_make_case())

        kwargs = fake_responses.last_call_kwargs
        assert kwargs["model"] == "gpt-5.4"
        assert kwargs["max_output_tokens"] == 1024
        assert kwargs["instructions"] == DEFAULT_SYSTEM_PROMPT

        # context_management rides in extra_body, not as a direct kwarg,
        # and the server expects it as a LIST of edit descriptors (probed
        # 2026-04-09: sending a single object produces
        # "expected an array of objects, but got an object instead").
        assert "context_management" not in kwargs
        extra_body = kwargs["extra_body"]
        assert extra_body["context_management"] == [
            {
                "type": "compaction",
                "compact_threshold": 55_000,
            }
        ]

    def test_custom_system_prompt_is_passed_through(self) -> None:
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses()
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(
            client=client,
            system_prompt="Custom disambiguation.",
        )
        runner.run(_make_case())

        assert fake_responses.last_call_kwargs["instructions"] == "Custom disambiguation."

    def test_default_system_prompt_disambiguates_roles(self) -> None:
        """The default system prompt must tell the model that compaction
        'you' refers to the user, not to the assistant."""
        from headroom.evals.runners.openai_compact_v2 import DEFAULT_SYSTEM_PROMPT

        lowered = DEFAULT_SYSTEM_PROMPT.lower()
        assert "user" in lowered
        assert "refers to the user" in lowered or "not describing you" in lowered

    def test_counts_multiple_compaction_items(self) -> None:
        """n_compactions should reflect the number of compaction output
        items, not just whether any exist."""
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses(n_compaction_items=3)
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(client=client, model="gpt-5.4")
        result = runner.run(_make_case())

        assert result.n_compactions == 3

    def test_zero_compaction_items_when_threshold_not_crossed(self) -> None:
        """If the server returns no compaction items, n_compactions == 0."""
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses(n_compaction_items=0)
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(client=client, model="gpt-5.4")
        result = runner.run(_make_case())

        assert result.n_compactions == 0
        assert result.error is None

    def test_error_returns_result_with_error_field(self) -> None:
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        class _RaisingResponses:
            def create(self, **kwargs: Any) -> None:
                raise RuntimeError("boom")

        client = type("C", (), {"responses": _RaisingResponses()})()
        runner = OpenAICompactV2Runner(client=client, model="gpt-5.4")
        result = runner.run(_make_case())

        assert result.answer == ""
        assert result.error is not None
        assert "boom" in result.error
        assert result.final_input_tokens == 0

    def test_cost_is_zero_for_unpriced_model(self) -> None:
        """When the model isn't in the pricing table, cost is 0.0 rather
        than a fabricated estimate. This keeps reports honest for
        preview models until real prices land in the table.

        Uses a deliberately nonsense model id so this test stays valid
        even as new OpenAI models get added to _PRICING."""
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses(input_tokens=100_000, output_tokens=500)
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(
            client=client, model="gpt-unicorn-preview-not-in-pricing"
        )
        result = runner.run(_make_case())

        assert result.cost_usd == 0.0

    def test_cost_is_computed_for_gpt_5_4(self) -> None:
        """Regression: gpt-5.4 was added to _PRICING in the cost retrofit
        commit. Make sure the runner actually computes a non-zero cost
        for it on a case with real token counts."""
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses(input_tokens=100_000, output_tokens=500)
        client = _FakeOpenAIClient(responses=fake_responses)
        runner = OpenAICompactV2Runner(client=client, model="gpt-5.4")
        result = runner.run(_make_case())

        # gpt-5.4: $2.50/M input, $15/M output
        # 100_000 input tokens × $2.50/M = $0.25
        # 500 output tokens × $15/M = $0.0075
        # total = $0.2575
        assert result.cost_usd == pytest.approx(0.2575, abs=1e-4)

    def test_cost_is_computed_for_priced_model(self) -> None:
        """When the model IS in the pricing table, cost is computed
        from response.usage."""
        from headroom.evals.runners.openai_compact_v2 import OpenAICompactV2Runner

        fake_responses = _FakeResponses(input_tokens=100_000, output_tokens=500)
        client = _FakeOpenAIClient(responses=fake_responses)
        # gpt-4o is in _PRICING: (2.50, 10.00) per 1M tokens
        runner = OpenAICompactV2Runner(client=client, model="gpt-4o")
        result = runner.run(_make_case())

        # 100000 * 2.50/1e6 + 500 * 10.00/1e6 = 0.250 + 0.005 = 0.255
        assert abs(result.cost_usd - 0.255) < 1e-6
