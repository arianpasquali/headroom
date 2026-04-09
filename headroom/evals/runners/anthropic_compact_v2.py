"""AnthropicCompactV2Runner — server-side `compact_20260112` compaction.

Wraps Anthropic's first-class automatic context compaction feature released
2026-01-12. Unlike the older `tool_runner(compaction_control=...)` mechanism
(which is tool-loop gated), this feature fires on plain `beta.messages.create`
via `context_management.edits=[{"type": "compact_20260112", ...}]` plus the
`compact-2026-01-12` beta header. It is supported on Opus 4.6 / Sonnet 4.6 /
Mythos Preview — **not** Sonnet 4.5.

Task-shape caveat
-----------------

Default out-of-the-box behaviour of `compact_20260112` exhibits a systematic
**role-confusion failure** on LongMemEval-style conversational fact-recall:
the compaction summary is inserted as an assistant-continuation block, and
second-person pronouns in the summary ("you graduated with X") are parsed by
the final answer call as self-referential, causing the model to reject its
own notes as "external third-party summary, possibly inaccurate."

Two probes on N=2 (Apr 9) established the fix:

1. Pass a ``system`` prompt that explicitly disambiguates the
   user/assistant roles and instructs the model to treat the compaction
   block as its own memory of what the USER said.
2. Pass a custom ``instructions`` parameter to the compaction edit that
   forces the summary to use **third-person** phrasing about "the user"
   and explicitly preserve verbatim values, numbers, and named entities.

With both fixes applied, case 1 ("What degree did I graduate with?" —
ground truth "Business Administration") is correctly answered. Case 2
("How long is my daily commute?" — ground truth "45 minutes each way")
still fails because the compaction summarizer is query-blind: it applies a
generic salience prior that preserves identity-defining facts (degrees,
jobs) but drops incidental-looking facts (commute times, favourite
restaurants) even when they happen to be the later query target. That
failure mode is intrinsic to prospective summarization and is the
meaningful comparison against Headroom's query-aware retrieval-style
compression.

The runner therefore ships with:

- ``system_prompt``: the role-disambiguation framing above (configurable).
- ``instructions``: the third-person compaction instructions (configurable).
- ``trigger_input_tokens``: when to fire (default 60_000, min 50_000).
- ``max_tokens``: answer/compaction max output (default 2048 — anything
  smaller truncates the summary below useful size).
"""

from __future__ import annotations

import json
import time

from headroom.evals.core import EvalCase
from headroom.evals.runners._rate_limit import retry_on_rate_limit
from headroom.evals.runners.direct_runners import _anthropic_rate_limit_exceptions
from headroom.evals.runners.provider_compaction import (
    CompactionResult,
    _cost_from_tokens,
    _count_tokens,
)

BETA_HEADER = "compact-2026-01-12"

DEFAULT_SYSTEM_PROMPT = (
    "You are Claude, an AI assistant. You are answering a question about a "
    "HUMAN USER based on a long prior conversation you had with them.\n\n"
    "IMPORTANT: If you see a compaction block containing a summary, it "
    "describes facts THE USER told you about THEMSELVES. It is NOT describing "
    "you. Phrases like 'you mentioned X' in the compaction block should be "
    "re-read as 'the user mentioned X about themselves' — the second-person "
    "pronoun refers to the user, because the compaction block is your record "
    "of what the user told you.\n\n"
    "You, Claude, do not have a degree, a commute, a family, a job, or any "
    "personal history. All such details in the compaction block are facts the "
    "USER shared with you during the conversation.\n\n"
    "When answering, use the facts from the compaction block directly, "
    "phrased as 'According to our prior conversation, you [the user] said X'."
)

DEFAULT_COMPACTION_INSTRUCTIONS = (
    "Summarize the prior conversation as factual notes about the human user. "
    "ALWAYS write facts in the third person about 'the user' — never use "
    "second-person 'you' statements, because those are ambiguous about whether "
    "they refer to the assistant or the user. Example: write 'The user said "
    "they graduated with a degree in Business Administration' NOT 'You "
    "graduated with Business Administration'. Preserve all specific facts the "
    "user mentioned about themselves — degrees, locations, commute times, "
    "family, preferences, dates, numbers, names — verbatim."
)


def _flatten_haystack(context: str) -> str:
    data = json.loads(context)
    sessions = data.get("haystack_sessions", [])
    return "\n\n".join(json.dumps(sess) for sess in sessions)


class AnthropicCompactV2Runner:
    """Run an EvalCase through Anthropic's server-side ``compact_20260112``.

    Parameters
    ----------
    client:
        An ``anthropic.Anthropic`` SDK client (injected for testability).
    model:
        Answer/compaction model. Must support the beta header; tested on
        ``claude-sonnet-4-6``.
    trigger_input_tokens:
        The ``input_tokens`` threshold at which the server triggers
        compaction. Minimum 50_000 per the docs, default 150_000 on the
        server side; this runner defaults to 60_000 so it fires on every
        LongMemEval case (haystacks cluster at ~110k).
    max_tokens:
        Output token budget. This bounds BOTH the compaction summary
        iteration AND the final answer iteration — the server uses the
        same cap for both. 2048 is the minimum that lets the summary
        retain useful detail; lower values truncate.
    system_prompt:
        Role-disambiguation system prompt. See module docstring for why
        this matters.
    compaction_instructions:
        Custom ``instructions`` passed to the compaction edit. Forces
        third-person summary phrasing.
    """

    def __init__(
        self,
        client,  # anthropic.Anthropic, injected
        model: str = "claude-sonnet-4-6",
        trigger_input_tokens: int = 60_000,
        max_tokens: int = 2048,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        compaction_instructions: str = DEFAULT_COMPACTION_INSTRUCTIONS,
    ) -> None:
        self._client = client
        self._model = model
        self._trigger_input_tokens = trigger_input_tokens
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._compaction_instructions = compaction_instructions

    def _rate_limited_create(self, **kwargs):
        """Call ``client.beta.messages.create`` with 429 retry/backoff."""

        def _do_call():
            return self._client.beta.messages.create(**kwargs)  # type: ignore[attr-defined]

        retry_exceptions = _anthropic_rate_limit_exceptions()
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

        start = time.monotonic()
        try:
            response = self._rate_limited_create(
                betas=[BETA_HEADER],
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_content}],
                context_management={
                    "edits": [
                        {
                            "type": "compact_20260112",
                            "trigger": {
                                "type": "input_tokens",
                                "value": self._trigger_input_tokens,
                            },
                            "instructions": self._compaction_instructions,
                        }
                    ]
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

        # Extract the answer text (the last text block in response.content).
        answer = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                answer = block.text
                # Don't break; take the last text block in case there are
                # multiple. compact_20260112 typically returns [compaction, text]
                # but the API shape allows multiple blocks.

        # Count compaction events from response.content (not usage.iterations,
        # which counts compaction-internal iterations).
        n_compaction_blocks = sum(
            1 for b in response.content if getattr(b, "type", None) == "compaction"
        )

        # Token / cost accounting from usage.iterations if available. Each
        # BetaMessageIterationUsage entry has input_tokens / output_tokens /
        # cache_creation_input_tokens / cache_read_input_tokens / type.
        usage = getattr(response, "usage", None)
        iterations = list(getattr(usage, "iterations", None) or [])

        compaction_iters = [it for it in iterations if getattr(it, "type", None) == "compaction"]
        message_iters = [it for it in iterations if getattr(it, "type", None) == "message"]

        # final_input_tokens is the input the final (post-compaction) message
        # iteration actually saw. If there was no compaction, fall back to
        # the top-level usage.input_tokens.
        if message_iters:
            final_input_tokens = message_iters[-1].input_tokens or 0
        elif usage is not None:
            final_input_tokens = getattr(usage, "input_tokens", 0) or 0
        else:
            final_input_tokens = 0

        # Sum cost across all iterations (each iteration is a separate
        # model invocation that Anthropic bills independently).
        total_cost = 0.0
        if iterations:
            for it in iterations:
                total_cost += _cost_from_tokens(
                    model=self._model,
                    input_tokens=getattr(it, "input_tokens", 0) or 0,
                    output_tokens=getattr(it, "output_tokens", 0) or 0,
                    cache_creation_tokens=getattr(it, "cache_creation_input_tokens", 0) or 0,
                    cache_read_tokens=getattr(it, "cache_read_input_tokens", 0) or 0,
                )
        elif usage is not None:
            total_cost = _cost_from_tokens(
                model=self._model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            )

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
            n_iterations=len(iterations) if iterations else 1,
            n_compactions=n_compaction_blocks,
            cost_usd=total_cost,
        )
