"""Rate-limit retry helper for compaction-compare runners.

Long-context LongMemEval / LongBench runs push single requests up to the
org-level 2M input-tokens/minute ceiling. When that happens, the Anthropic
SDK's default 2-retry budget is not enough — the request needs to wait for
the rolling window to decay, which takes 30–60s.

`retry_on_rate_limit` wraps a callable so that `RateLimitError` (or any
exception class passed in `retry_exceptions`) triggers a bounded retry loop
that honors the server-provided `retry-after` header, falling back to
exponential backoff when the header is missing.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def _parse_retry_after(exc: Exception) -> float | None:
    """Extract the `retry-after` hint (seconds) from an exception's HTTP response.

    Returns None when the exception has no response, no headers, or the header
    is missing / unparseable. Callers should fall back to their own backoff
    strategy when this returns None.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after") if hasattr(headers, "get") else None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def retry_on_rate_limit(
    fn: Callable[[], T],
    *,
    retry_exceptions: tuple[type[BaseException], ...],
    max_attempts: int = 6,
    base_backoff_seconds: float = 5.0,
    max_backoff_seconds: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> T:
    """Call `fn()`, retrying on rate-limit errors with `retry-after`-aware backoff.

    On each rate-limit error, waits for:
      - `retry-after` seconds from the response header, if provided, OR
      - exponential backoff (`base_backoff_seconds` × 2 ** attempt), capped at
        `max_backoff_seconds`, otherwise.

    After `max_attempts` failed attempts, re-raises the last error.

    Args:
        fn: Zero-arg callable that issues the rate-limited request.
        retry_exceptions: Exception types that trigger a retry (e.g.
            `(anthropic.RateLimitError,)`). Any other exception propagates
            immediately.
        max_attempts: Maximum total attempts (including the first). Must be >= 1.
        base_backoff_seconds: Base for exponential backoff when `retry-after`
            is unavailable.
        max_backoff_seconds: Ceiling on any single sleep. Prevents runaway waits.
        sleep: Injectable sleep function. Tests pass a no-op.
        log: Optional callable for progress messages. Defaults to stderr when None.

    Returns:
        Whatever `fn()` returns on success.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    if log is None:
        log = lambda msg: print(msg, file=sys.stderr, flush=True)  # noqa: E731

    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except retry_exceptions as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                break

            retry_after = _parse_retry_after(exc)
            if retry_after is None:
                wait = min(base_backoff_seconds * (2**attempt), max_backoff_seconds)
                reason = "exponential backoff"
            else:
                wait = min(retry_after, max_backoff_seconds)
                reason = "retry-after header"

            log(
                f"  rate-limited; sleeping {wait:.1f}s ({reason}), "
                f"attempt {attempt + 1}/{max_attempts}"
            )
            sleep(wait)

    assert last_exc is not None  # unreachable: loop either returns or sets last_exc
    raise last_exc
