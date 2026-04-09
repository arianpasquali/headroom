"""Provider-native compaction runners for LongMemEval comparisons.

This module provides two adapters that run an EvalCase through each
provider's built-in compaction mechanism and return per-case metrics.

Design note: We use tiktoken (cl100k_base) for token estimation on both
providers. Anthropic doesn't ship tiktoken, but cl100k_base counts are a
reasonable ballpark for cross-provider comparison purposes.

The "chunked tool call" harness is intentional: LongMemEval questions are
naturally single-turn, so we artificially expose a read_history(chunk_id)
tool to force multi-iteration and give the SDK's compaction logic room to
fire. The comparison is "compression mechanism vs compression mechanism",
not "natural workflow vs natural workflow".
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import tiktoken

from headroom.evals.core import EvalCase


@dataclass
class CompactionResult:
    """Per-case metrics from a compaction-arm run.

    Two latency numbers are tracked:

    - ``latency_ms`` is the **wall-clock** end-to-end time, including any
      summarization / compaction work. This is what an all-synchronous
      implementation pays.
    - ``user_visible_latency_ms`` is the time the **user** waits for the
      final answer. For synchronous arms (baseline, headroom_default,
      anthropic_compact_20260112 with the compaction inline, and the default
      summary_prompt runner) this equals ``latency_ms``. For proactive /
      background arms (anthropic_session_memory, where the cookbook pattern
      runs summarization off the critical path), this excludes the
      summarization time — it reflects what a production deployment of that
      pattern would actually show to end users.

    Cost accounting:

    - ``cost_usd`` is the summed cost of every API call the arm made for this
      case, computed against the per-model pricing in
      ``headroom/providers/anthropic.py::ANTHROPIC_PRICING``. Includes
      ``input + cache_read + output`` token charges; cache creation is
      charged at input rate per Anthropic's billing model. Defaults to 0.0
      for test fixtures that don't populate it.
    """

    case_id: str
    answer: str  # the model's final answer
    original_input_tokens: int  # naive token count if we'd sent the full haystack
    final_input_tokens: int  # actual tokens used (sum across iterations, post-compaction)
    compression_ratio: float  # 1 - (final / original)
    latency_ms: float  # wall-clock end-to-end (includes any summarization)
    n_iterations: int  # how many iterations the loop ran
    n_compactions: int  # how many compaction events fired
    user_visible_latency_ms: float | None = None  # time the user actually waits; None → same as latency_ms
    cost_usd: float = 0.0  # summed API cost for this case
    error: str | None = None

    def __post_init__(self) -> None:
        if self.user_visible_latency_ms is None:
            self.user_visible_latency_ms = self.latency_ms


def _count_tokens(text: str) -> int:
    """Count tokens using cl100k_base (ballpark for both Anthropic and OpenAI)."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# Cost accounting
# ---------------------------------------------------------------------------


def _pricing_for(model: str) -> dict[str, float]:
    """Return per-million-token pricing for a Claude model.

    Looks up the explicit ``ANTHROPIC_PRICING`` table first, then falls back
    to pattern matching (opus / sonnet / haiku) against the model slug, and
    finally to the ``_UNKNOWN_CLAUDE_DEFAULT``. Returns a dict with keys
    ``input``, ``output``, ``cached_input`` (all in dollars per 1e6 tokens).
    """
    from headroom.providers.anthropic import (
        ANTHROPIC_PRICING,
        _PATTERN_DEFAULTS,
        _UNKNOWN_CLAUDE_DEFAULT,
    )

    if model in ANTHROPIC_PRICING:
        return ANTHROPIC_PRICING[model]
    slug = model.lower()
    for family, defaults in _PATTERN_DEFAULTS.items():
        if family in slug:
            return defaults["pricing"]  # type: ignore[return-value]
    return _UNKNOWN_CLAUDE_DEFAULT["pricing"]  # type: ignore[return-value]


def _cost_from_tokens(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute USD cost for a single API call.

    Anthropic bills cache creation at the normal input rate and cache reads
    at the cached-input rate. Our simplified model follows the same shape.
    """
    p = _pricing_for(model)
    return (
        (input_tokens + cache_creation_tokens) * p["input"] / 1_000_000
        + cache_read_tokens * p["cached_input"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
    )


def _cost_from_usage(model: str, usage) -> float:  # noqa: ANN001 — usage shape varies
    """Compute USD cost from an anthropic SDK ``Usage`` or ``BetaUsage``."""
    return _cost_from_tokens(
        model=model,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )


def _split_into_chunks(text: str, chunk_token_size: int) -> list[str]:
    """Split text into roughly equal chunks of ~chunk_token_size tokens."""
    enc = tiktoken.get_encoding("cl100k_base")
    token_ids = enc.encode(text)
    chunks = []
    for start in range(0, len(token_ids), chunk_token_size):
        chunk_ids = token_ids[start : start + chunk_token_size]
        chunks.append(enc.decode(chunk_ids))
    return chunks if chunks else [text]


def _flatten_haystack(context: str) -> str:
    """Parse LongMemEval JSON context and flatten haystack_sessions to text."""
    data = json.loads(context)
    sessions = data.get("haystack_sessions", [])
    return "\n\n".join(json.dumps(sess) for sess in sessions)


# ---------------------------------------------------------------------------
# Anthropic compaction runner
# ---------------------------------------------------------------------------


class AnthropicCompactionRunner:
    """Run an EvalCase through Anthropic's beta.messages.tool_runner with
    compaction_control enabled.

    The runner splits the haystack into chunks and exposes two dummy tools:
      - read_history(chunk_id) — returns one chunk of the haystack
      - submit_answer(answer) — captures the model's final answer

    The system prompt instructs the model to read all chunks in order then
    call submit_answer. This forces multi-iteration so compaction has a
    chance to fire before the final answer is produced.
    """

    def __init__(
        self,
        client,  # anthropic.Anthropic instance (injected for testability)
        model: str = "claude-sonnet-4-5-20250514",
        max_tokens: int = 1024,
        context_token_threshold: int = 50_000,
        chunk_token_size: int = 10_000,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._context_token_threshold = context_token_threshold
        self._chunk_token_size = chunk_token_size

        # Per-run state (reset in run())
        self._chunks: list[str] = []
        self._answer: str = ""

    def run(self, case: EvalCase) -> CompactionResult:
        from anthropic.lib.tools import beta_tool  # local import for testability

        # Reset per-run state
        self._chunks = []
        self._answer = ""

        # 1. Parse and flatten haystack
        haystack_text = _flatten_haystack(case.context)

        # 2. Count original tokens
        original_input_tokens = _count_tokens(haystack_text)

        # 3. Split into chunks
        self._chunks = _split_into_chunks(haystack_text, self._chunk_token_size)
        n_chunks = len(self._chunks)

        # 4. Define dummy tools
        runner_self = self  # closure reference

        @beta_tool
        def read_history(chunk_id: int) -> str:
            """Read one chunk of the conversation history by index."""
            if 0 <= chunk_id < len(runner_self._chunks):
                return runner_self._chunks[chunk_id]
            return f"Error: chunk_id {chunk_id} out of range (0..{len(runner_self._chunks) - 1})"

        @beta_tool
        def submit_answer(answer: str) -> str:
            """Submit the final answer to the question."""
            runner_self._answer = answer
            return "Answer submitted."

        # 5. Build initial messages
        system_prompt = (
            f"You have access to a long conversation history split into {n_chunks} chunks. "
            f"Read them in order using read_history(0), read_history(1), ..., "
            f"read_history({n_chunks - 1}). "
            f"After reading all chunks, answer the following question using submit_answer."
        )
        user_message = {"role": "user", "content": case.query}
        messages = [user_message]

        # 6. Run via tool_runner with compaction_control
        compaction_control = {
            "enabled": True,
            "context_token_threshold": self._context_token_threshold,
        }

        start = time.monotonic()
        final_input_tokens = 0
        n_iterations = 0
        n_compactions = 0
        prev_input_tokens: int | None = None

        try:
            runner = self._client.beta.messages.tool_runner(
                model=self._model,
                max_tokens=self._max_tokens,
                tools=[read_history, submit_answer],
                messages=messages,
                system=system_prompt,
                compaction_control=compaction_control,
            )

            for message in runner:
                usage = message.usage
                iter_input_tokens = (
                    usage.input_tokens
                    + (usage.cache_creation_input_tokens or 0)
                    + (usage.cache_read_input_tokens or 0)
                )
                final_input_tokens += iter_input_tokens
                n_iterations += 1

                # Detect compaction: token count drops significantly vs prior iteration
                if prev_input_tokens is not None and iter_input_tokens < prev_input_tokens * 0.5:
                    n_compactions += 1
                prev_input_tokens = iter_input_tokens

                # Stop early once the answer is submitted
                if self._answer:
                    break

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=final_input_tokens,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                n_iterations=n_iterations,
                n_compactions=n_compactions,
                error=str(exc),
            )

        latency_ms = (time.monotonic() - start) * 1000
        compression_ratio = (
            1 - (final_input_tokens / original_input_tokens) if original_input_tokens > 0 else 0.0
        )

        return CompactionResult(
            case_id=case.id,
            answer=self._answer,
            original_input_tokens=original_input_tokens,
            final_input_tokens=final_input_tokens,
            compression_ratio=compression_ratio,
            latency_ms=latency_ms,
            n_iterations=n_iterations,
            n_compactions=n_compactions,
        )


# ---------------------------------------------------------------------------
# OpenAI compaction runner
# ---------------------------------------------------------------------------


class OpenAICompactionRunner:
    """Run an EvalCase through OpenAI's responses API with compaction.

    Chains responses.create calls (one per chunk) using previous_response_id
    to build multi-turn state. When accumulated tokens cross compact_threshold,
    calls responses.compact() before the next chunk to compress the context.
    """

    def __init__(
        self,
        client,  # openai.OpenAI instance (injected for testability)
        model: str = "gpt-4o-mini",
        max_tokens: int = 1024,
        compact_threshold: int = 50_000,
        chunk_token_size: int = 10_000,
    ) -> None:
        # Verify compact endpoint exists in this SDK version
        if not hasattr(client.responses, "compact"):
            raise NotImplementedError(
                "OpenAI compaction unavailable in this SDK version: "
                "client.responses.compact() not found."
            )
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._compact_threshold = compact_threshold
        self._chunk_token_size = chunk_token_size

    def run(self, case: EvalCase) -> CompactionResult:
        # 1. Parse and flatten haystack
        haystack_text = _flatten_haystack(case.context)

        # 2. Count original tokens
        original_input_tokens = _count_tokens(haystack_text)

        # 3. Split into chunks
        chunks = _split_into_chunks(haystack_text, self._chunk_token_size)
        n_chunks = len(chunks)

        system_instructions = (
            f"You have access to a long conversation history split into {n_chunks} chunks. "
            "I will feed them to you one at a time. Read and remember each chunk. "
            "After the final chunk you will be asked the question."
        )

        start = time.monotonic()
        final_input_tokens = 0
        n_iterations = 0
        n_compactions = 0
        answer = ""
        last_response_id: str | None = None
        cumulative_tokens = 0

        try:
            # 4. Feed each chunk as a separate response.create call
            for i, chunk in enumerate(chunks):
                create_kwargs: dict = {
                    "model": self._model,
                    "input": f"[Chunk {i + 1}/{n_chunks}]\n\n{chunk}",
                    "instructions": system_instructions,
                    "max_output_tokens": self._max_tokens,
                }
                if last_response_id is not None:
                    create_kwargs["previous_response_id"] = last_response_id

                # 5. Compact before create if threshold exceeded
                if cumulative_tokens >= self._compact_threshold and last_response_id is not None:
                    compacted = self._client.responses.compact(
                        model=self._model,
                        previous_response_id=last_response_id,
                    )
                    last_response_id = compacted.id
                    # Reset cumulative; use compacted token count if available
                    cumulative_tokens = getattr(
                        getattr(compacted, "usage", None), "input_tokens", 0
                    )
                    n_compactions += 1
                    # Update previous_response_id in the pending create call
                    create_kwargs["previous_response_id"] = last_response_id

                response = self._client.responses.create(**create_kwargs)
                chunk_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
                final_input_tokens += chunk_tokens
                cumulative_tokens += chunk_tokens
                last_response_id = response.id
                n_iterations += 1

            # 6. Final turn: ask the question
            final_create_kwargs: dict = {
                "model": self._model,
                "input": case.query,
                "instructions": system_instructions,
                "max_output_tokens": self._max_tokens,
            }
            if last_response_id is not None:
                final_create_kwargs["previous_response_id"] = last_response_id

            # Compact before final question if still over threshold
            if cumulative_tokens >= self._compact_threshold and last_response_id is not None:
                compacted = self._client.responses.compact(
                    model=self._model,
                    previous_response_id=last_response_id,
                )
                last_response_id = compacted.id
                n_compactions += 1
                final_create_kwargs["previous_response_id"] = last_response_id

            final_response = self._client.responses.create(**final_create_kwargs)
            final_q_tokens = getattr(getattr(final_response, "usage", None), "input_tokens", 0)
            final_input_tokens += final_q_tokens
            n_iterations += 1

            # 7. Extract answer
            answer = getattr(final_response, "output_text", "") or ""

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=final_input_tokens,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                n_iterations=n_iterations,
                n_compactions=n_compactions,
                error=str(exc),
            )

        latency_ms = (time.monotonic() - start) * 1000
        compression_ratio = (
            1 - (final_input_tokens / original_input_tokens) if original_input_tokens > 0 else 0.0
        )

        return CompactionResult(
            case_id=case.id,
            answer=answer,
            original_input_tokens=original_input_tokens,
            final_input_tokens=final_input_tokens,
            compression_ratio=compression_ratio,
            latency_ms=latency_ms,
            n_iterations=n_iterations,
            n_compactions=n_compactions,
        )
