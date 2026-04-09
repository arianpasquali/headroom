"""Floor-test runners for methodological robustness of the Headroom comparison.

These two runners are designed to answer a single skeptic question:

    Is Headroom winning because of its query-aware *selection*, or just
    because 54% less text = less distractor load regardless of what's kept?

Both runners compress the LongMemEval haystack to the same target ratio that
Headroom's ContentRouter lands on (~54%), but without Headroom's query-aware
relevance scoring:

- ``DumbTruncationLastNRunner`` keeps the **last N%** of the tokenized
  haystack and drops the rest. Models naive recency bias — "just keep the
  most recent turns."
- ``RandomChunkDropRunner`` deterministically drops randomly-selected chunks
  until the target ratio is reached. Models "any compression at all" without
  any structural preservation.

If these arms get **close to baseline quality** on the same N, Headroom's
ContentRouter selection is doing real work. If they get **close to Headroom
quality**, then "just less text" is the load-bearing factor and Headroom's
ML stack is overengineered for the workload.

Either result is publishable. The point of these runners is to make the
question answerable in one commit, not to advocate for a particular answer.

Design notes
------------

- Both runners use the same ``_flatten_haystack`` + ``_count_tokens`` helpers
  as the direct runners, so compression-ratio accounting is apples-to-apples
  with ``BaselineRunner`` and ``HeadroomDefaultRunner``.
- Both runners accept a ``target_compression_ratio`` (default 0.54 to
  match Headroom's observed ratio on LongMemEval). Setting this to 0.0
  turns the runner into a pass-through; setting it to 0.997 models the
  ``anthropic_compact_v2`` operating point for a curve plot.
- ``RandomChunkDropRunner`` uses a **deterministic seed derived from the
  case id** so reruns of the same eval produce identical results. This is
  important for reproducibility — we don't want N=30 quality scores to
  depend on numpy's global RNG state.
- Neither runner makes any API calls during the compression step. The only
  API call is the final answer call, identical in shape to
  ``BaselineRunner`` (single-turn, no iteration loop).
"""

from __future__ import annotations

import hashlib
import random
import time

import tiktoken

from headroom.evals.core import EvalCase
from headroom.evals.runners.direct_runners import (
    _anthropic_rate_limit_exceptions,
    _call_anthropic,
    _call_openai,
    _flatten_haystack,
)
from headroom.evals.runners.provider_compaction import CompactionResult

DEFAULT_TARGET_COMPRESSION_RATIO = 0.54  # matches Headroom's observed ratio
DEFAULT_CHUNK_TOKEN_SIZE = 2_000


def _tiktoken_encoder():
    return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_tiktoken_encoder().encode(text))


def _truncate_last_n_tokens(text: str, keep_ratio: float) -> tuple[str, int, int]:
    """Keep only the last ``keep_ratio`` fraction of the tokenized text.

    Returns ``(compressed_text, original_token_count, kept_token_count)``.
    Token-level slicing is done via tiktoken so the compression ratio is
    accurate in the same units the other runners report.
    """
    enc = _tiktoken_encoder()
    token_ids = enc.encode(text)
    original_n = len(token_ids)
    if original_n == 0 or keep_ratio >= 1.0:
        return text, original_n, original_n
    keep_n = max(1, int(round(original_n * keep_ratio)))
    kept_ids = token_ids[-keep_n:]
    return enc.decode(kept_ids), original_n, keep_n


def _random_chunk_drop(
    text: str, keep_ratio: float, chunk_token_size: int, seed: int
) -> tuple[str, int, int]:
    """Split into ~chunk_token_size chunks and randomly drop enough chunks to hit keep_ratio.

    Returns ``(compressed_text, original_token_count, kept_token_count)``.
    Drop order is determined by a seeded Random instance so results are
    reproducible across runs of the same eval.
    """
    enc = _tiktoken_encoder()
    token_ids = enc.encode(text)
    original_n = len(token_ids)
    if original_n == 0 or keep_ratio >= 1.0:
        return text, original_n, original_n

    # Split into chunks of chunk_token_size each.
    chunks: list[list[int]] = []
    for start in range(0, original_n, chunk_token_size):
        chunks.append(token_ids[start : start + chunk_token_size])

    # How many chunks do we need to keep?
    total_chunks = len(chunks)
    n_keep_chunks = max(1, int(round(total_chunks * keep_ratio)))

    # Randomly select which chunks to keep, but preserve original order.
    rng = random.Random(seed)
    indices = list(range(total_chunks))
    kept_indices = sorted(rng.sample(indices, n_keep_chunks))

    kept_ids: list[int] = []
    for i in kept_indices:
        kept_ids.extend(chunks[i])

    return enc.decode(kept_ids), original_n, len(kept_ids)


def _case_seed(case_id: str) -> int:
    """Deterministic per-case seed for reproducible random chunk drops."""
    digest = hashlib.sha256(case_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big")


class DumbTruncationLastNRunner:
    """Floor-test arm: keep only the last N% of the tokenized haystack.

    This is the simplest possible 'compression' — no selection logic, just
    throw away everything before the final ``keep_ratio`` fraction of
    tokens. It models a naive 'keep recent' baseline similar to OpenAI's
    ``truncation="auto"`` but applied locally and forced to match Headroom's
    compression ratio rather than only firing above the model's context
    window.

    Parameters
    ----------
    client:
        Anthropic or OpenAI SDK client.
    provider:
        "anthropic" or "openai".
    model:
        Answer model id.
    max_tokens:
        Max output tokens for the single answer call.
    target_compression_ratio:
        Fraction of the *original* tokens to drop. Default 0.54 matches
        Headroom's observed compression on LongMemEval. The runner keeps
        ``(1 - target_compression_ratio)`` fraction of the input.
    """

    def __init__(
        self,
        client: object,
        provider: str,
        model: str,
        max_tokens: int = 1024,
        target_compression_ratio: float = DEFAULT_TARGET_COMPRESSION_RATIO,
    ) -> None:
        self._client = client
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._target_compression_ratio = target_compression_ratio

    def run(self, case: EvalCase) -> CompactionResult:
        haystack_blob = _flatten_haystack(case.context)
        keep_ratio = 1.0 - self._target_compression_ratio
        compressed_text, original_input_tokens, final_input_tokens = _truncate_last_n_tokens(
            haystack_blob, keep_ratio
        )
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


class RandomChunkDropRunner:
    """Floor-test arm: randomly drop chunks until compression ratio hits target.

    Splits the haystack into fixed-size chunks of ``chunk_token_size`` tokens,
    then uses a deterministic per-case random seed to drop enough chunks to
    reach ``target_compression_ratio``. Preserved chunks stay in their
    original order so the final text is still readable as a sequential
    context, just with holes.

    This is the fairest "any compression, no structure" floor test. If
    Headroom beats this at the same ratio, Headroom's relevance-scoring is
    earning its keep. If Headroom ties this, Headroom's ML stack is
    overkill.

    Parameters
    ----------
    client, provider, model, max_tokens:
        Same as ``DumbTruncationLastNRunner``.
    target_compression_ratio:
        Same as ``DumbTruncationLastNRunner``.
    chunk_token_size:
        Chunk granularity. 2_000 tokens is a reasonable balance — small
        enough that the randomness has real resolution on a 125k haystack
        (~62 chunks), large enough that individual chunks are still
        coherent conversational turns.
    """

    def __init__(
        self,
        client: object,
        provider: str,
        model: str,
        max_tokens: int = 1024,
        target_compression_ratio: float = DEFAULT_TARGET_COMPRESSION_RATIO,
        chunk_token_size: int = DEFAULT_CHUNK_TOKEN_SIZE,
    ) -> None:
        self._client = client
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._target_compression_ratio = target_compression_ratio
        self._chunk_token_size = chunk_token_size

    def run(self, case: EvalCase) -> CompactionResult:
        haystack_blob = _flatten_haystack(case.context)
        keep_ratio = 1.0 - self._target_compression_ratio
        seed = _case_seed(case.id)
        compressed_text, original_input_tokens, final_input_tokens = _random_chunk_drop(
            haystack_blob,
            keep_ratio=keep_ratio,
            chunk_token_size=self._chunk_token_size,
            seed=seed,
        )
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
