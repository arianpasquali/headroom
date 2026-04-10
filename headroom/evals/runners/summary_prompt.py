"""Feature A: custom summary-prompt runner for LongMemEval comparisons.

Uses a dedicated Haiku 4.5 summarization call (structured JSON output) to
compress older context when the conversation approaches the context-fill
threshold.  Returns a CompactionResult so the multi-arm driver can treat it
identically to AnthropicCompactionRunner and OpenAICompactionRunner.
"""

from __future__ import annotations

import json
import time

import tiktoken

from headroom.evals.core import EvalCase
from headroom.evals.runners._rate_limit import retry_on_rate_limit
from headroom.evals.runners.direct_runners import _anthropic_rate_limit_exceptions
from headroom.evals.runners.provider_compaction import (
    CompactionResult,
    _cost_from_usage,
)

DEFAULT_SUMMARY_PROMPT = """\
You are summarizing a long conversation history so an assistant can answer a follow-up question without re-reading the full transcript.

Read the conversation history below and produce a STRICT JSON object with these keys:

{
  "decisions":      [list of explicit decisions or commitments the user made],
  "constraints":    [list of explicit constraints, preferences, or rules the user stated],
  "rejected_paths": [list of options the user explicitly rejected or ruled out],
  "file_refs":      [list of files, URLs, IDs, or external resources mentioned],
  "facts":          [list of standalone factual statements about the user or their context]
}

Be concise. Each list item should be one sentence. Omit anything that is small talk, repeated, or not load-bearing for future questions. Output ONLY the JSON object, no preamble or commentary.

CONVERSATION HISTORY:
"""


def _count_tokens_list(messages: list[dict]) -> int:
    """Count tokens across a list of message dicts."""
    enc = tiktoken.get_encoding("cl100k_base")
    total = 0
    for msg in messages:
        total += len(enc.encode(msg.get("content", "")))
    return total


def _count_tokens(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _split_into_chunks(text: str, chunk_token_size: int) -> list[str]:
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


class SummaryPromptRunner:
    """Feature A: dedicated Haiku 4.5 summarization call.

    Splits the LongMemEval haystack into chunks and replays them in turn-style.
    When a turn would push cumulative tokens above the trigger fill, the runner
    invokes a single summarization call (Haiku 4.5, structured JSON output) to
    replace the older chunks with a structured summary, then continues. The
    final call asks the question against (summary + recent chunks).

    Caps:
    - Never trigger on the first `min_turn` chunks (default 3) — too little
      context to summarize meaningfully.
    - At most `max_cycles` summarization calls per case (default 3).

    The "context fill" metric is measured against `model_context_window`,
    not the runner's own state, so the trigger fires at the same point a real
    LLM caller would hit pressure.
    """

    def __init__(
        self,
        client,  # anthropic.Anthropic, injected
        answer_model: str = "claude-sonnet-4-5-20250514",
        summary_model: str = "claude-haiku-4-5",
        model_context_window: int = 200_000,
        trigger_fill: float = 0.70,  # fraction of window
        keep_recent: int = 4,  # most recent chunks always preserved
        min_turn: int = 3,  # never summarize before this many chunks
        max_cycles: int = 3,  # cap on summarization calls
        chunk_token_size: int = 10_000,
        max_tokens: int = 1024,
        summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
    ) -> None:
        self._client = client
        self._answer_model = answer_model
        self._summary_model = summary_model
        self._model_context_window = model_context_window
        self._trigger_fill = trigger_fill
        self._keep_recent = keep_recent
        self._min_turn = min_turn
        self._max_cycles = max_cycles
        self._chunk_token_size = chunk_token_size
        self._max_tokens = max_tokens
        self._summary_prompt = summary_prompt

    def _rate_limited_create(self, **kwargs):
        """Call `client.messages.create` with 429 retry/backoff.

        Wraps both the summarization and the final answer calls so a single
        rate-limited request doesn't mark the whole case as failed. When the
        anthropic SDK is unavailable (e.g. in tests using a fake client), the
        retry wrapper becomes a pass-through.
        """

        def _do_call():
            return self._client.messages.create(**kwargs)

        retry_exceptions = _anthropic_rate_limit_exceptions()
        if not retry_exceptions:
            return _do_call()
        return retry_on_rate_limit(_do_call, retry_exceptions=retry_exceptions)

    def run(self, case: EvalCase) -> CompactionResult:
        # 1. Parse and flatten haystack
        haystack_text = _flatten_haystack(case.context)

        # 2. Count original tokens and split into chunks
        original_input_tokens = _count_tokens(haystack_text)
        chunks = _split_into_chunks(haystack_text, self._chunk_token_size)

        messages: list[dict] = []
        cycles_used = 0
        summary_latency_ms = 0.0
        total_cost = 0.0

        start = time.monotonic()

        try:
            # 3. Replay loop
            for i, chunk in enumerate(chunks):
                messages.append({"role": "user", "content": chunk})
                current_tokens = _count_tokens_list(messages)

                # Check if we should trigger summarization
                if (
                    i + 1 >= self._min_turn
                    and cycles_used < self._max_cycles
                    and current_tokens / self._model_context_window >= self._trigger_fill
                ):
                    # 4. Summarization step
                    # Identify messages to summarize (all except the last keep_recent)
                    keep = self._keep_recent
                    if len(messages) <= keep:
                        # Not enough messages to split; skip
                        pass
                    else:
                        messages_to_summarize = messages[:-keep]
                        recent_messages = messages[-keep:]

                        prompt = (
                            self._summary_prompt
                            + "\n\n"
                            + "\n---\n".join(m["content"] for m in messages_to_summarize)
                        )

                        sum_start = time.monotonic()
                        summary_response = self._rate_limited_create(
                            model=self._summary_model,
                            max_tokens=self._max_tokens,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        summary_latency_ms += (time.monotonic() - sum_start) * 1000
                        sum_usage = getattr(summary_response, "usage", None)
                        if sum_usage is not None:
                            total_cost += _cost_from_usage(
                                self._summary_model, sum_usage
                            )

                        summary_text = summary_response.content[0].text

                        summary_message = {
                            "role": "user",
                            "content": (
                                "<previous_conversation_summary>\n"
                                + summary_text
                                + "\n</previous_conversation_summary>"
                            ),
                        }

                        messages = [summary_message] + recent_messages
                        cycles_used += 1

            # After all chunks loaded, append the question
            messages.append({"role": "user", "content": case.query})

            # 5. Count final input tokens (for the answer call only)
            final_input_tokens = _count_tokens_list(messages)

            # Final answer call
            answer_response = self._rate_limited_create(
                model=self._answer_model,
                max_tokens=self._max_tokens,
                messages=messages,
            )
            answer = answer_response.content[0].text
            ans_usage = getattr(answer_response, "usage", None)
            if ans_usage is not None:
                total_cost += _cost_from_usage(self._answer_model, ans_usage)

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000 + summary_latency_ms
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=0,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                n_iterations=len(chunks) + 1,
                n_compactions=cycles_used,
                cost_usd=total_cost,
                error=str(exc),
            )

        # 6. Token accounting
        compression_ratio = (
            1 - (final_input_tokens / original_input_tokens) if original_input_tokens > 0 else 0.0
        )

        # Total latency includes summarization overhead (this is the
        # *synchronous* version of the session memory pattern — summaries
        # block the answer path, so wall-clock == user-visible).
        latency_ms = (time.monotonic() - start) * 1000

        # 7. Compaction event count
        n_compactions = cycles_used
        n_iterations = len(chunks) + 1  # chunks + final answer call

        return CompactionResult(
            case_id=case.id,
            answer=answer,
            original_input_tokens=original_input_tokens,
            final_input_tokens=final_input_tokens,
            compression_ratio=compression_ratio,
            latency_ms=latency_ms,
            n_iterations=n_iterations,
            n_compactions=n_compactions,
            cost_usd=total_cost,
        )
