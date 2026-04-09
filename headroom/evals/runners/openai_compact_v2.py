"""OpenAICompactV2Runner — server-side Responses API compaction.

Wraps OpenAI's first-class automatic context compaction feature in the
Responses API. Unlike the older ``OpenAICompactionRunner`` in
``provider_compaction.py`` (which chains chunked ``responses.create`` calls
and explicitly invokes ``responses.compact()`` between chunks — and which
was found to be a no-op on ``gpt-4o-mini`` during the Apr 8 probe because
the older model doesn't actually support the feature), this runner issues
a **single** ``responses.create`` call that passes
``context_management={"type": "compaction", "compact_threshold": N}`` and
lets the server automatically compact mid-stream when the rendered token
count crosses the threshold.

Why a new runner
----------------

The reproduction-comparison doc (§ 4.1 of
``research/2026-04-09-streamlit-reproduction-comparison.md``) previously
concluded that OpenAI's ``responses.compact`` was "an analytics endpoint"
based on a probe against ``gpt-4o-mini``. The current OpenAI docs (April
2026) directly contradict that: compaction is a real primitive on the
GPT-5.x family, the returned compaction item *is* chainable (append to the
next ``input`` array, or use ``previous_response_id``), and the docs
explicitly state *"do not prune /responses/compact output. The returned
window is the canonical next context window"*. The most plausible
explanation is that compaction is **gated on model version**: gpt-4o-mini
returns a degenerate analytics-only response even though the endpoint
exists, while GPT-5.3-codex / GPT-5.4 produce real compaction items.

This runner therefore:

- Targets GPT-5.x (default ``gpt-5.4``).
- Uses the server-side ``context_management`` parameter, not the
  standalone ``/responses/compact`` chained-chunks pattern.
- Mirrors ``AnthropicCompactV2Runner`` in shape so the two can be
  compared apples-to-apples in the compaction-compare sweep.

Role-confusion caveat
---------------------

Anthropic's ``compact_20260112`` exhibited a systematic role-confusion
failure on LongMemEval (second-person pronouns in the summary were parsed
by the final answer call as self-referential). That failure mode was
worked around in ``AnthropicCompactV2Runner`` with a custom system prompt
and third-person ``instructions`` field. A 2-case smoke against
``gpt-5.4`` on 2026-04-09 (``longmemeval_e47becba``, ``longmemeval_118b2229``)
showed **both cases answered correctly** — including the commute case
that Anthropic's compact_v2 explicitly fails on. On n=2 this is
suggestive, not conclusive: a proper head-to-head at n≥20 is needed
before claiming anything about salience-prior differences between the
two vendors' compaction implementations. The role-disambiguation system
prompt is retained as a belt-and-braces default.

Compression-metric caveat (IMPORTANT for report interpretation)
---------------------------------------------------------------

The ``OpenAI Responses API`` ``ResponseUsage`` type exposes only:
``input_tokens``, ``input_tokens_details.cached_tokens``, ``output_tokens``,
``output_tokens_details.reasoning_tokens``, and ``total_tokens``. **There is
no field that reports post-compaction input tokens.** The server does
whatever internal context management it does, but billing — and therefore
``usage.input_tokens`` — reflects the full input the caller sent, not
what the model internally processed after compaction.

This runner sets ``final_input_tokens = usage.input_tokens`` (the
billable number) and derives ``compression_ratio`` from it. On the first
smoke run this produced ``compression_ratio ≈ 0.01`` even though
``n_compactions == 1``, because 1% represents billable-token drift, not
true post-compaction state. **Do not compare ``compression_ratio`` for
``openai_compact_v2`` against the same field for any other arm** — it
measures a strictly different quantity. Cross-arm compression comparisons
on this arm are only meaningful against a matched baseline run (same
input, same model, ``context_management`` omitted) using latency or
downstream cost as the diffed signal. Such a paired-baseline measurement
is tracked as a follow-up; the runner does not perform it today.

Until that measurement lands, interpret this arm's numbers as:

- ``n_compactions``: **valid** — did the server trigger compaction at all?
- ``answer`` (via judge): **valid** — did the compacted state preserve
  enough context to answer the question?
- ``latency_ms``: **valid** — wall-clock cost of the compaction path,
  comparable across arms.
- ``compression_ratio``: **N/A for cross-arm comparisons** — billable-
  token drift only. Expect it to hover near 0 even when compaction fires.

Configurable knobs:

- ``trigger_input_tokens``: the ``compact_threshold`` passed to the
  server (default 60_000, matching the Anthropic v2 default so that
  compaction fires on every LongMemEval case).
- ``max_output_tokens``: the Responses API ``max_output_tokens`` cap
  (default 2048).
- ``system_prompt``: role-disambiguation text passed as ``instructions``
  on the Responses API call (the Responses API's system-message
  equivalent).
"""

from __future__ import annotations

import json
import time

from headroom.evals.core import EvalCase
from headroom.evals.runners._rate_limit import retry_on_rate_limit
from headroom.evals.runners.provider_compaction import (
    CompactionResult,
    _count_tokens,
)

DEFAULT_SYSTEM_PROMPT = (
    "You are an AI assistant answering a question about a HUMAN USER based "
    "on a long prior conversation you had with them.\n\n"
    "IMPORTANT: If you see a compaction item in the context, it describes "
    "facts THE USER told you about THEMSELVES. It is NOT describing you. "
    "Phrases like 'you mentioned X' in a compaction item should be re-read "
    "as 'the user mentioned X about themselves' — the second-person pronoun "
    "refers to the user, because the compaction item is your record of "
    "what the user told you.\n\n"
    "You do not have a degree, a commute, a family, a job, or any personal "
    "history. All such details in the compaction item are facts the USER "
    "shared with you during the conversation.\n\n"
    "When answering, use the facts from the compaction item directly, "
    "phrased as 'According to our prior conversation, you [the user] said X'."
)


def _openai_rate_limit_exceptions() -> tuple[type[BaseException], ...]:
    """Lazily resolve the openai SDK's RateLimitError class.

    Kept out of module-level imports so tests can run without the SDK
    installed and so module import never hard-fails in environments that
    only use the Anthropic path. Returns an empty tuple when the SDK is
    missing, which makes ``retry_on_rate_limit`` a pass-through.
    """
    try:
        import openai  # type: ignore[import-not-found]
    except ImportError:
        return ()
    cls = getattr(openai, "RateLimitError", None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return (cls,)
    return ()


def _flatten_haystack(context: str) -> str:
    """Parse LongMemEval JSON context and flatten haystack_sessions to text."""
    data = json.loads(context)
    sessions = data.get("haystack_sessions", [])
    return "\n\n".join(json.dumps(sess) for sess in sessions)


def _cost_from_openai_usage(model: str, usage) -> float:  # noqa: ANN001
    """Best-effort USD cost from an OpenAI Responses API ``usage`` object.

    Looks up ``model`` in ``headroom.providers.openai._PRICING``. Returns
    0.0 if the model is not in the pricing table — explicitly NOT an
    estimate, so that reports for unpriced models don't silently report
    fabricated numbers. When the model lands in the table, input and
    output tokens are billed at the published rates.
    """
    if usage is None:
        return 0.0

    try:
        from headroom.providers.openai import _PRICING
    except ImportError:
        return 0.0

    pricing = _PRICING.get(model)
    if pricing is None:
        return 0.0

    input_rate, output_rate = pricing  # per 1M tokens
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


class OpenAICompactV2Runner:
    """Run an EvalCase through OpenAI's Responses API server-side compaction.

    Parameters
    ----------
    client:
        An ``openai.OpenAI`` SDK client (injected for testability).
    model:
        Answer/compaction model. Must support the ``context_management``
        parameter — tested on ``gpt-5.4``.
    trigger_input_tokens:
        The ``compact_threshold`` passed to ``context_management``. This
        is the token count at which the server triggers a compaction
        pass mid-response. Default 60_000 so it fires on every
        LongMemEval case (haystacks cluster at ~110k).
    max_output_tokens:
        Responses API output token budget. This bounds the final answer;
        the compaction summary is server-internal and not subject to
        this cap. Default 2048.
    system_prompt:
        Role-disambiguation system prompt passed via the Responses API
        ``instructions`` parameter. See module docstring for why this
        matters on LongMemEval-style workloads.
    """

    def __init__(
        self,
        client,  # openai.OpenAI, injected
        model: str = "gpt-5.4",
        trigger_input_tokens: int = 60_000,
        max_output_tokens: int = 2048,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._client = client
        self._model = model
        self._trigger_input_tokens = trigger_input_tokens
        self._max_output_tokens = max_output_tokens
        self._system_prompt = system_prompt

    def _rate_limited_create(self, **kwargs):
        """Call ``client.responses.create`` with 429 retry/backoff."""

        def _do_call():
            return self._client.responses.create(**kwargs)  # type: ignore[attr-defined]

        retry_exceptions = _openai_rate_limit_exceptions()
        if not retry_exceptions:
            return _do_call()
        return retry_on_rate_limit(_do_call, retry_exceptions=retry_exceptions)

    def run(self, case: EvalCase) -> CompactionResult:
        haystack_text = _flatten_haystack(case.context)
        original_input_tokens = _count_tokens(haystack_text)
        user_content = (
            f"Here is the full prior conversation between you and the user:\n\n"
            f"{haystack_text}\n\n"
            f"Now the user asks: {case.query}\n\n"
            f"Answer using facts from the prior conversation."
        )

        # The OpenAI Python SDK (tested on 2.15.0) does not yet expose
        # `context_management` as a typed parameter on responses.create —
        # passing it as a direct kwarg raises
        # `got an unexpected keyword argument 'context_management'` from
        # the SDK's Pydantic layer before any HTTP round-trip. Use the
        # SDK-documented `extra_body` passthrough so the field lands in
        # the raw POST /responses body and reaches the server.
        #
        # Wire shape probed on 2026-04-09: the server explicitly rejects
        # a single object with `{"error": {"message": "Invalid type for
        # 'context_management': expected an array of objects, but got an
        # object instead."}}`. The correct shape is therefore a LIST of
        # edit descriptors — we wrap our single compaction edit in a list
        # to match. The inner keys (`type`, `compact_threshold`) are still
        # best-guessed from the guide language; if a future server error
        # names a different inner key, update here AND in the test
        # `test_passes_context_management_via_extra_body` in lockstep.
        start = time.monotonic()
        try:
            response = self._rate_limited_create(
                model=self._model,
                input=user_content,
                instructions=self._system_prompt,
                max_output_tokens=self._max_output_tokens,
                extra_body={
                    "context_management": [
                        {
                            "type": "compaction",
                            "compact_threshold": self._trigger_input_tokens,
                        }
                    ],
                },
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=0,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                n_iterations=1,
                n_compactions=0,
                cost_usd=0.0,
                error=str(exc),
            )

        latency_ms = (time.monotonic() - start) * 1000

        # Answer: Responses API convention is `response.output_text`. Fall
        # back to scanning `response.output` for a text output item if
        # output_text is missing or empty.
        answer = getattr(response, "output_text", "") or ""
        output_items = list(getattr(response, "output", None) or [])
        if not answer and output_items:
            for item in output_items:
                if getattr(item, "type", None) in ("message", "text", "output_text"):
                    text = getattr(item, "text", None) or getattr(item, "content", None)
                    if isinstance(text, str):
                        answer = text
                        break

        # Count compaction events by scanning output items for type="compaction".
        # The exact type name is not yet publicly documented for the OpenAI
        # Responses API compaction item; "compaction" is the canonical guess
        # based on the guide language. If a real probe reveals a different
        # name, update this check.
        n_compaction_items = sum(
            1 for item in output_items if getattr(item, "type", None) == "compaction"
        )

        # Token / cost accounting from response.usage.
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0 if usage is not None else 0

        # IMPORTANT: `usage.input_tokens` is the billable input count for
        # the request — i.e. what the caller sent, NOT what the model
        # processed internally after the server's compaction pass.
        # The Responses API ResponseUsage type (openai 2.15.0) has no
        # "post-compaction input tokens" field; see the module docstring
        # "Compression-metric caveat" for why. On the 2026-04-09 smoke
        # this produced compression_ratio ≈ 0.01 while n_compactions == 1,
        # exactly as the caveat predicts. Do not compare this field
        # against other arms' compression_ratio without a matched-baseline
        # diff — it measures billable drift, not effective compression.
        final_input_tokens = input_tokens

        total_cost = _cost_from_openai_usage(self._model, usage)

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
            n_iterations=1,
            n_compactions=n_compaction_items,
            cost_usd=total_cost,
        )
