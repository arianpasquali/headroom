"""Simple baseline runners for LongMemEval cross-arm comparisons.

Two non-iterative runners that serve as baselines:

- BaselineRunner: sends the full haystack in a single LLM call.
- HeadroomDefaultRunner: pre-compresses with ContentRouter, then makes
  one LLM call with the compressed content.

Both produce CompactionResult instances compatible with the other arms.
"""

from __future__ import annotations

import json
import time

import tiktoken

from headroom.evals.core import EvalCase
from headroom.evals.runners._rate_limit import retry_on_rate_limit
from headroom.evals.runners.provider_compaction import (
    CompactionResult,
    _cost_from_usage,
)


def _anthropic_rate_limit_exceptions() -> tuple[type[BaseException], ...]:
    """Lazily resolve the anthropic SDK's RateLimitError class.

    Kept out of module-level imports so tests can run without the SDK installed
    and so import of this module doesn't hard-fail on environments that only
    use the OpenAI path. Returns an empty tuple when the SDK is missing, which
    makes `retry_on_rate_limit` a pass-through.

    Only `RateLimitError` (HTTP 429) is retried; broader `APIStatusError`
    covers non-retryable failures like 400/401/404 that should propagate.
    """
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        return ()
    cls = getattr(anthropic, "RateLimitError", None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return (cls,)
    return ()


def _count_tokens(text: str) -> int:
    """Count tokens using cl100k_base (ballpark for both Anthropic and OpenAI)."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _flatten_haystack(context: str) -> str:
    """Parse LongMemEval JSON context and flatten haystack_sessions to text."""
    data = json.loads(context)
    sessions = data.get("haystack_sessions", [])
    return "\n\n".join(json.dumps(sess) for sess in sessions)


def _call_anthropic(
    client: object, model: str, max_tokens: int, input_text: str
) -> tuple[str, float]:
    """Make a single Anthropic messages.create call.

    Returns ``(answer_text, cost_usd)``. Wraps the SDK call in a
    ``retry_on_rate_limit`` loop so long-context runs that exceed the org-level
    tokens/minute ceiling wait out the rolling window instead of hard-failing
    the whole case. See ``_rate_limit.py`` for backoff behaviour.

    Cost is computed from the response ``usage`` object using the
    per-model pricing registered in
    ``headroom/providers/anthropic.py::ANTHROPIC_PRICING``, which is
    falling back to pattern-matching (opus/sonnet/haiku) for unknown slugs.
    """

    def _do_call() -> tuple[str, float]:
        response = client.messages.create(  # type: ignore[attr-defined]
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": input_text}],
        )
        text = response.content[0].text
        # Test fakes may not provide a usage attribute; default cost to 0.0.
        usage = getattr(response, "usage", None)
        cost = _cost_from_usage(model, usage) if usage is not None else 0.0
        return text, cost

    retry_exceptions = _anthropic_rate_limit_exceptions()
    if not retry_exceptions:
        return _do_call()
    return retry_on_rate_limit(_do_call, retry_exceptions=retry_exceptions)


def _call_openai(
    client: object, model: str, max_tokens: int, input_text: str
) -> tuple[str, float]:
    """Make a single OpenAI responses.create call.

    Returns ``(answer_text, cost_usd)``. Cost is computed from
    ``response.usage.input_tokens`` and ``response.usage.output_tokens``
    using the per-model input/output token prices from
    ``litellm.model_cost``. For models not in that table, or when the
    response lacks a usage object (e.g. test fakes), cost silently falls
    back to 0.0.
    """
    response = client.responses.create(  # type: ignore[attr-defined]
        model=model,
        input=input_text,
        max_output_tokens=max_tokens,
    )
    text = getattr(response, "output_text", "") or ""

    # Cost accounting. Guarded so test fakes without a usage object still
    # return cost=0.0 without raising.
    cost = 0.0
    usage = getattr(response, "usage", None)
    if usage is not None:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cost = _openai_cost_from_tokens(model, input_tokens, output_tokens)

    return text, cost


def _openai_cost_from_tokens(model: str, input_tokens: int, output_tokens: int) -> float:
    """Look up per-token prices for ``model`` in ``litellm.model_cost`` and compute cost.

    Returns 0.0 if litellm is unavailable, the model is unknown, or the
    entry is missing price fields. All failures are silent because cost
    accounting is a reporting convenience, not a correctness requirement
    — a missing price shouldn't take down the run.
    """
    try:
        import litellm
    except ImportError:
        return 0.0

    model_cost = getattr(litellm, "model_cost", {}) or {}
    entry = model_cost.get(model)
    if entry is None:
        return 0.0
    in_rate = entry.get("input_cost_per_token")
    out_rate = entry.get("output_cost_per_token")
    if in_rate is None or out_rate is None:
        return 0.0
    return float(in_rate) * int(input_tokens) + float(out_rate) * int(output_tokens)


class BaselineRunner:
    """Sends the full LongMemEval haystack to the LLM in a single call.

    No compression is performed. This is the simplest possible baseline:
    the model receives everything and is asked the question.
    """

    def __init__(
        self,
        client: object,
        provider: str,  # "anthropic" or "openai"
        model: str,
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens

    def run(self, case: EvalCase) -> CompactionResult:
        haystack_blob = _flatten_haystack(case.context)
        original_input_tokens = _count_tokens(haystack_blob)
        input_text = haystack_blob + "\n\n" + case.query

        start = time.monotonic()
        try:
            if self._provider == "anthropic":
                answer, cost = _call_anthropic(
                    self._client, self._model, self._max_tokens, input_text
                )
            else:
                answer, cost = _call_openai(
                    self._client, self._model, self._max_tokens, input_text
                )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=original_input_tokens,
                compression_ratio=0.0,
                latency_ms=latency_ms,
                n_iterations=1,
                n_compactions=0,
                error=str(exc),
            )

        latency_ms = (time.monotonic() - start) * 1000
        return CompactionResult(
            case_id=case.id,
            answer=answer,
            original_input_tokens=original_input_tokens,
            final_input_tokens=original_input_tokens,
            compression_ratio=0.0,
            latency_ms=latency_ms,
            n_iterations=1,
            n_compactions=0,
            cost_usd=cost,
        )


class HeadroomDefaultRunner:
    """Pre-compresses the haystack with Headroom's ContentRouter, then sends one LLM call.

    The compression ratio is computed in tokens (not characters) for
    cross-arm comparability with the provider compaction runners.
    """

    def __init__(
        self,
        client: object,
        provider: str,  # "anthropic" or "openai"
        model: str,
        max_tokens: int = 1024,
        router_config: object = None,  # ContentRouterConfig | None
    ) -> None:
        self._client = client
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._router_config = router_config

    def run(self, case: EvalCase) -> CompactionResult:
        from headroom.transforms.content_router import ContentRouter, ContentRouterConfig

        haystack_blob = _flatten_haystack(case.context)
        original_input_tokens = _count_tokens(haystack_blob)

        # Build ContentRouter (uses default config if none provided)
        config = self._router_config if self._router_config is not None else ContentRouterConfig()
        router = ContentRouter(config=config)

        # Compress with question-aware mode
        compression_result = router.compress(content=haystack_blob, question=case.query)
        compressed_text = compression_result.compressed

        final_input_tokens = _count_tokens(compressed_text)
        compression_ratio = (
            1 - (final_input_tokens / original_input_tokens) if original_input_tokens > 0 else 0.0
        )

        input_text = compressed_text + "\n\n" + case.query

        start = time.monotonic()
        try:
            if self._provider == "anthropic":
                answer, cost = _call_anthropic(
                    self._client, self._model, self._max_tokens, input_text
                )
            else:
                answer, cost = _call_openai(
                    self._client, self._model, self._max_tokens, input_text
                )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return CompactionResult(
                case_id=case.id,
                answer="",
                original_input_tokens=original_input_tokens,
                final_input_tokens=final_input_tokens,
                compression_ratio=compression_ratio,
                latency_ms=latency_ms,
                n_iterations=1,
                n_compactions=0,
                error=str(exc),
            )

        latency_ms = (time.monotonic() - start) * 1000
        return CompactionResult(
            case_id=case.id,
            answer=answer,
            original_input_tokens=original_input_tokens,
            final_input_tokens=final_input_tokens,
            compression_ratio=compression_ratio,
            latency_ms=latency_ms,
            n_iterations=1,
            n_compactions=0,
            cost_usd=cost,
        )
