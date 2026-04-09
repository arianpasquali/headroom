"""AnthropicSessionMemoryRunner — cookbook client-side compaction pattern.

Implements Anthropic's documented "session memory compaction" pattern from
https://platform.claude.com/cookbook/misc-session-memory-compaction — a
client-side approach for long conversational applications that's separate
from the server-side ``compact_20260112`` feature. The cookbook advertises
three design moves:

1. **Proactive background summarization.** Rather than summarize reactively
   when the context fills up (making the user wait), run the summarization
   call on a background thread as soon as cumulative tokens cross a low
   threshold. By the time the user hits the hard limit, the session memory
   is already in place.
2. **Prompt caching on the summarization call.** Mark prior messages with
   ``cache_control: ephemeral`` so that repeated partial re-summarizations
   during a running conversation read most of their input from cache at
   ~10x reduced cost.
3. **Structured 6-section conversational schema.** User Intent / Completed
   Work / Key Facts About The User / Active Work / Pending Tasks / Key
   References. Designed for casual conversational recall, not SWE planning.

Measurement honesty notes
-------------------------

**One-shot evaluation is not the cookbook's natural habitat.** The cookbook
is designed for a running conversation that accumulates over many turns.
Two things work against us when we apply it to LongMemEval:

1. **Caching doesn't pay off cross-case.** Each LongMemEval case has a
   fresh haystack, so ``cache_creation_input_tokens`` burns full input
   price on every case and ``cache_read_input_tokens`` is always zero.
   We still pass ``cache_control: ephemeral`` because that's what the
   cookbook prescribes, but the discount never materialises in this
   benchmark shape. Report it honestly.

2. **"Background summarization" has no background to run in.** With one
   question per case, there's no existing conversation for the summary
   to be computed alongside. We measure ``latency_ms`` as the real
   wall-clock end-to-end (summary + answer, synchronous), and
   ``user_visible_latency_ms`` as just the final answer call — an
   idealised upper bound representing what a production deployment
   would show if the summary had been pre-computed. This is a
   **favourable assumption for the cookbook pattern**, not a neutral
   measurement, and must be called out in the report.

Summarizer model choice
-----------------------

The cookbook uses Haiku for cost reasons. Our N=2 smoke showed Haiku 4.5
meta-confusing when summarizing a 125k-token haystack (it wrote "the user
is summarizing a prior conversation" treating the input as metadata about
a summarization task, not as the conversation to summarize). That's a
known weakness of small models on long nested inputs. The runner defaults
to Haiku 4.5 (to match the cookbook literally) but exposes
``summary_model`` as a knob so a Sonnet-summarizer variant can be run as
an ablation. Haiku failures on the N=50 run will be reported honestly.
"""

from __future__ import annotations

import json
import time

from headroom.evals.core import EvalCase
from headroom.evals.runners._rate_limit import retry_on_rate_limit
from headroom.evals.runners.direct_runners import _anthropic_rate_limit_exceptions
from headroom.evals.runners.provider_compaction import (
    CompactionResult,
    _cost_from_usage,
    _count_tokens,
)

# 6-section conversational schema from the cookbook, reframed to use
# third-person about "the user" to avoid the self-reference pronoun
# ambiguity we saw on the compact_20260112 probe.
SESSION_MEMORY_PROMPT = """\
You are summarizing a prior conversation between a user and an assistant \
so the assistant can answer the user's follow-up question without \
re-reading the full transcript. Produce your summary with the following \
sections. Write all facts in the third person about "the user" — never use \
second-person pronouns in the summary, because those are ambiguous about \
whether they refer to the assistant or the user.

## User Intent
The user's core request, goals, or recurring themes in the conversation.

## Completed Work
What the assistant has already helped the user with, or what topics have \
been fully discussed.

## Key Facts About The User
Every specific factual detail the user has shared about themselves: \
degrees, locations, family, commute times, hobbies, preferences, dates, \
numbers, and named entities. Preserve values verbatim. This section is the \
most important — never omit a specific user-stated fact, number, name, or \
value.

## Active Work
What the user is currently working on or curious about.

## Pending Tasks
Anything the user has asked for that has not yet been addressed.

## Key References
Files, URLs, product names, places, or other named entities the user has \
mentioned.

Be concise where you can, but never omit a specific user-stated fact. \
Wrap your summary in <session_memory></session_memory> tags.
"""

DEFAULT_ANSWER_SYSTEM = (
    "You are an assistant continuing a long conversation with a user. "
    "You have a session memory summary of the prior conversation. Use the "
    "facts in the session memory to answer the user's question directly. "
    "All 'the user' references in the session memory refer to the person "
    "you're now speaking with. The session memory is your own notes on "
    "what the user previously told you — treat the facts in it as reliable."
)


def _flatten_haystack(context: str) -> str:
    data = json.loads(context)
    sessions = data.get("haystack_sessions", [])
    return "\n\n".join(json.dumps(sess) for sess in sessions)


class AnthropicSessionMemoryRunner:
    """Run an EvalCase through the cookbook session memory pattern.

    Parameters
    ----------
    client:
        An ``anthropic.Anthropic`` SDK client (injected for testability).
    answer_model:
        The model that answers the final question, given the session
        memory summary plus the question. Defaults to ``claude-sonnet-4-6``.
    summary_model:
        The model that produces the session memory. Cookbook uses Haiku
        for cost; we default to ``claude-haiku-4-5-20251001`` to match.
    summary_prompt:
        The summarization prompt. Defaults to the 6-section schema from
        the cookbook, reframed to third person.
    answer_system_prompt:
        The system prompt on the answer call. Tells the model how to
        treat the session memory block.
    max_summary_tokens:
        Output budget for the summarization call. 2048 is enough for the
        6-section schema at LongMemEval scale.
    max_answer_tokens:
        Output budget for the final answer call. 512 is enough for
        LongMemEval-style short answers.
    """

    def __init__(
        self,
        client,  # anthropic.Anthropic, injected
        answer_model: str = "claude-sonnet-4-6",
        summary_model: str = "claude-haiku-4-5-20251001",
        summary_prompt: str = SESSION_MEMORY_PROMPT,
        answer_system_prompt: str = DEFAULT_ANSWER_SYSTEM,
        max_summary_tokens: int = 2048,
        max_answer_tokens: int = 512,
    ) -> None:
        self._client = client
        self._answer_model = answer_model
        self._summary_model = summary_model
        self._summary_prompt = summary_prompt
        self._answer_system_prompt = answer_system_prompt
        self._max_summary_tokens = max_summary_tokens
        self._max_answer_tokens = max_answer_tokens

    def _rate_limited_create(self, **kwargs):
        def _do_call():
            return self._client.messages.create(**kwargs)  # type: ignore[attr-defined]

        retry_exceptions = _anthropic_rate_limit_exceptions()
        if not retry_exceptions:
            return _do_call()
        return retry_on_rate_limit(_do_call, retry_exceptions=retry_exceptions)

    def run(self, case: EvalCase) -> CompactionResult:
        haystack_text = _flatten_haystack(case.context)
        original_input_tokens = _count_tokens(haystack_text)

        start_wall = time.monotonic()
        total_cost = 0.0

        # --------------------------------------------------------------------
        # Step 1: Background summarization call.
        # --------------------------------------------------------------------
        # We measure its latency separately so we can subtract it from
        # wall-clock to get the idealised user-visible latency. This
        # assumes the summary would have been pre-computed in production.
        summary_start = time.monotonic()
        try:
            summary_response = self._rate_limited_create(
                model=self._summary_model,
                max_tokens=self._max_summary_tokens,
                system=[
                    {
                        "type": "text",
                        "text": self._summary_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"CONVERSATION HISTORY:\n\n{haystack_text}",
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                ],
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start_wall) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=0,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                user_visible_latency_ms=0.0,
                n_iterations=1,
                n_compactions=0,
                cost_usd=total_cost,
                error=f"summary call failed: {exc}",
            )

        summary_latency_ms = (time.monotonic() - summary_start) * 1000
        sum_usage = getattr(summary_response, "usage", None)
        if sum_usage is not None:
            total_cost += _cost_from_usage(self._summary_model, sum_usage)
        summary_text = summary_response.content[0].text

        # --------------------------------------------------------------------
        # Step 2: Final answer call with just (session memory + question).
        # --------------------------------------------------------------------
        # This is what the user actually waits for in the cookbook's
        # proactive-background deployment.
        answer_user_content = (
            "Here is the session memory from our prior conversation:\n\n"
            + summary_text
            + f"\n\nNow I'm asking: {case.query}"
        )

        answer_start = time.monotonic()
        try:
            answer_response = self._rate_limited_create(
                model=self._answer_model,
                max_tokens=self._max_answer_tokens,
                system=self._answer_system_prompt,
                messages=[{"role": "user", "content": answer_user_content}],
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start_wall) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=0,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                user_visible_latency_ms=(time.monotonic() - answer_start) * 1000,
                n_iterations=2,
                n_compactions=1,
                cost_usd=total_cost,
                error=f"answer call failed: {exc}",
            )

        answer_latency_ms = (time.monotonic() - answer_start) * 1000
        wall_ms = (time.monotonic() - start_wall) * 1000

        ans_usage = getattr(answer_response, "usage", None)
        if ans_usage is not None:
            total_cost += _cost_from_usage(self._answer_model, ans_usage)

        answer = answer_response.content[0].text

        # Compression accounting: final_input_tokens is what the answer
        # call actually sent (session memory + question), not the
        # original haystack size.
        final_input_tokens = (
            getattr(ans_usage, "input_tokens", 0) or 0
            if ans_usage is not None
            else _count_tokens(answer_user_content)
        )
        compression_ratio = (
            1 - (final_input_tokens / original_input_tokens) if original_input_tokens > 0 else 0.0
        )

        # User-visible latency is just the answer call, modeling a
        # production deployment where the summary was pre-computed on a
        # background thread.
        user_visible_ms = answer_latency_ms

        return CompactionResult(
            case_id=case.id,
            answer=answer,
            original_input_tokens=original_input_tokens,
            final_input_tokens=final_input_tokens,
            compression_ratio=compression_ratio,
            latency_ms=wall_ms,
            user_visible_latency_ms=user_visible_ms,
            n_iterations=2,  # summary + answer
            n_compactions=1,
            cost_usd=total_cost,
        )
