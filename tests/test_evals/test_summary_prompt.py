"""Tests for SummaryPromptRunner (Feature A: custom summary prompt baseline).

All tests use fake clients — no real API calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from headroom.evals.core import EvalCase
from headroom.evals.runners.provider_compaction import CompactionResult
from headroom.evals.runners.summary_prompt import SummaryPromptRunner

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_SMALL_SESSIONS = [
    [
        {"role": "user", "content": "I need a Python web app using FastAPI."},
        {"role": "assistant", "content": "Sure, I can help with that."},
    ],
    [
        {"role": "user", "content": "I want to use PostgreSQL as the database."},
        {"role": "assistant", "content": "Great choice for a production app."},
    ],
    [
        {"role": "user", "content": "I rejected SQLite because it does not scale."},
        {"role": "assistant", "content": "Understood."},
    ],
]

_SMALL_CONTEXT = json.dumps(
    {
        "haystack_sessions": _SMALL_SESSIONS,
        "haystack_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
    }
)

_SMALL_CASE = EvalCase(
    id="test-summary-1",
    context=_SMALL_CONTEXT,
    query="What database did the user choose?",
    ground_truth="PostgreSQL",
)


def _make_large_case(n_repeat: int = 15) -> EvalCase:
    """Build a case with a large haystack to force multiple chunks."""
    session_template = [
        {
            "role": "user",
            "content": (
                "This is a detailed message about the project requirements. "
                "We need to build a scalable microservices architecture with "
                "Kubernetes orchestration and Redis caching. The system must "
                "handle at least 10000 requests per second with sub-100ms latency. "
                "We have strict GDPR compliance requirements and need audit logging "
                "for all data access. The frontend will use React with TypeScript. "
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Understood. I will design the architecture accordingly. "
                "We will use Kubernetes for container orchestration, Redis for "
                "distributed caching, and implement comprehensive audit logging. "
                "The React TypeScript frontend will connect via a GraphQL API gateway. "
            ),
        },
    ]
    sessions = [session_template for _ in range(n_repeat)]
    context = json.dumps(
        {
            "haystack_sessions": sessions,
            "haystack_dates": [f"2024-01-{i + 1:02d}" for i in range(n_repeat)],
        }
    )
    return EvalCase(
        id="test-summary-large",
        context=context,
        query="What database caching layer was chosen?",
        ground_truth="Redis",
    )


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class _FakeContent:
    text: str = ""


@dataclass
class _FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class _FakeMessage:
    content: list = field(default_factory=lambda: [_FakeContent(text="fake response")])
    usage: _FakeUsage = field(default_factory=_FakeUsage)


class _FakeMessages:
    """Records all messages.create calls and returns canned responses."""

    def __init__(
        self,
        summary_response: str = '{"decisions": [], "constraints": [], "rejected_paths": [], "file_refs": [], "facts": []}',
        answer_response: str = "Redis",
    ):
        self.calls: list[dict[str, Any]] = []
        self._summary_response = summary_response
        self._answer_response = answer_response
        self._call_count = 0

    def create(self, **kwargs) -> _FakeMessage:
        self.calls.append(kwargs)
        self._call_count += 1
        # First N-1 calls (if any) are summarization calls (use summary_model)
        # Last call is the answer call (uses answer_model)
        # We detect by model name
        model = kwargs.get("model", "")
        if "haiku" in model.lower():
            return _FakeMessage(
                content=[_FakeContent(text=self._summary_response)],
                usage=_FakeUsage(input_tokens=500, output_tokens=100),
            )
        else:
            return _FakeMessage(
                content=[_FakeContent(text=self._answer_response)],
                usage=_FakeUsage(input_tokens=200, output_tokens=30),
            )


class _FakeAnthropicClient:
    """Stub that mimics anthropic.Anthropic with messages.create."""

    def __init__(
        self,
        summary_response: str = '{"decisions": [], "constraints": [], "rejected_paths": [], "file_refs": [], "facts": []}',
        answer_response: str = "Redis",
    ):
        self.messages = _FakeMessages(summary_response, answer_response)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSummaryPromptRunner:
    def _make_runner(self, client=None, **kwargs) -> SummaryPromptRunner:
        if client is None:
            client = _FakeAnthropicClient()
        return SummaryPromptRunner(client, **kwargs)

    def test_returns_compaction_result_with_answer(self):
        runner = self._make_runner(trigger_fill=1.0)  # never trigger summarization
        result = runner.run(_SMALL_CASE)
        assert isinstance(result, CompactionResult)
        assert result.case_id == "test-summary-1"
        assert result.answer == "Redis"
        assert result.error is None

    def test_no_summarization_below_trigger(self):
        """With trigger_fill very high, no summarization should occur."""
        runner = self._make_runner(trigger_fill=1.0)
        result = runner.run(_SMALL_CASE)
        assert result.n_compactions == 0

    def test_summarization_fires_when_trigger_crosses(self):
        """With trigger_fill very low and enough chunks, summarization fires."""
        case = _make_large_case(n_repeat=15)
        runner = self._make_runner(
            trigger_fill=0.0,  # fires immediately after min_turn
            chunk_token_size=50,
            min_turn=3,
            max_cycles=3,
        )
        result = runner.run(case)
        assert result.n_compactions >= 1

    def test_min_turn_blocks_early_summarization(self):
        """With min_turn larger than chunk count, no summarization fires."""
        # Use small case to get few chunks, set min_turn higher than chunk count
        runner = self._make_runner(
            trigger_fill=0.0,  # would trigger immediately otherwise
            chunk_token_size=100_000,  # large chunks so we get only 1 chunk
            min_turn=10,  # require 10 chunks before summarizing
        )
        result = runner.run(_SMALL_CASE)
        assert result.n_compactions == 0

    def test_max_cycles_caps_summarization(self):
        """Summarization is capped at max_cycles even with trigger_fill=0."""
        case = _make_large_case(n_repeat=20)
        max_cycles = 2
        runner = self._make_runner(
            trigger_fill=0.0,
            chunk_token_size=50,
            min_turn=3,
            max_cycles=max_cycles,
        )
        result = runner.run(case)
        assert result.n_compactions == max_cycles

    def test_summary_prompt_is_passed_to_haiku_call(self):
        """Verify the summary model and custom prompt are used in summarization calls."""
        case = _make_large_case(n_repeat=15)
        fake_client = _FakeAnthropicClient()
        custom_prompt = "CUSTOM SUMMARY PROMPT: "
        runner = SummaryPromptRunner(
            fake_client,
            summary_model="claude-haiku-4-5",
            trigger_fill=0.0,
            chunk_token_size=50,
            min_turn=3,
            max_cycles=1,
            summary_prompt=custom_prompt,
        )
        runner.run(case)
        # Find the summarization call (uses haiku model)
        summary_calls = [
            c for c in fake_client.messages.calls if "haiku" in c.get("model", "").lower()
        ]
        assert len(summary_calls) >= 1
        call = summary_calls[0]
        assert call["model"] == "claude-haiku-4-5"
        # The prompt content should contain our custom prompt
        msg_content = call["messages"][0]["content"]
        assert custom_prompt in msg_content

    def test_answer_call_uses_answer_model(self):
        """Verify the final answer call uses answer_model, not summary_model."""
        case = _make_large_case(n_repeat=15)
        fake_client = _FakeAnthropicClient()
        answer_model = "claude-sonnet-4-5-20250514"
        runner = SummaryPromptRunner(
            fake_client,
            answer_model=answer_model,
            summary_model="claude-haiku-4-5",
            trigger_fill=0.0,
            chunk_token_size=50,
            min_turn=3,
            max_cycles=1,
        )
        runner.run(case)
        # Last call should be the answer call with the answer model
        assert len(fake_client.messages.calls) >= 1
        last_call = fake_client.messages.calls[-1]
        assert last_call["model"] == answer_model

    def test_compression_ratio_when_summarization_fires(self):
        """After summarization, final_input_tokens < original_input_tokens."""
        case = _make_large_case(n_repeat=15)
        runner = self._make_runner(
            trigger_fill=0.0,
            chunk_token_size=50,
            min_turn=3,
            max_cycles=1,
        )
        result = runner.run(case)
        assert result.n_compactions >= 1
        assert result.original_input_tokens > 0
        assert result.final_input_tokens > 0
        # compression_ratio should be computed correctly
        expected = 1 - (result.final_input_tokens / result.original_input_tokens)
        assert abs(result.compression_ratio - expected) < 1e-6

    def test_keep_recent_chunks_preserved_after_summary(self):
        """The last keep_recent chunks should appear in the final messages context."""
        case = _make_large_case(n_repeat=20)
        fake_client = _FakeAnthropicClient()
        keep_recent = 2
        runner = SummaryPromptRunner(
            fake_client,
            trigger_fill=0.0,
            chunk_token_size=50,
            min_turn=3,
            max_cycles=1,
            keep_recent=keep_recent,
        )
        runner.run(case)
        # Find the answer call (last call, uses sonnet model)
        last_call = fake_client.messages.calls[-1]
        messages = last_call["messages"]
        # First message after summarization should be the summary wrapper
        # Then keep_recent chunk messages, then the question
        # Total should be at least keep_recent + 2 (summary + question)
        assert len(messages) >= keep_recent + 2
        # The first message should contain the summary XML tag
        assert "<previous_conversation_summary>" in messages[0]["content"]
