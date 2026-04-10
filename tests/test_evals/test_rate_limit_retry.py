"""Tests for the `retry_on_rate_limit` helper and its runner integration.

The helper exists to absorb 429s during long-context LongMemEval / LongBench
runs that push single requests past the org-level 2M tokens/minute ceiling.
These tests cover:

1. Direct helper behaviour — happy path, `retry-after` honouring, exponential
   fallback, attempt caps, non-retryable exceptions.
2. Runner integration — a fake Anthropic client that raises twice then
   succeeds completes cleanly through `BaselineRunner`, proving the wiring
   holds end-to-end.

Tests inject a fake sleep to keep the suite fast and an in-memory log sink so
the retry-progress messages don't pollute test output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from headroom.evals.core import EvalCase
from headroom.evals.runners._rate_limit import retry_on_rate_limit
from headroom.evals.runners.direct_runners import BaselineRunner

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRateLimit(Exception):
    """Stand-in for anthropic.RateLimitError.

    Has the shape retry_on_rate_limit reads: `.response.headers.get(...)`.
    Using a test-local class avoids depending on the anthropic SDK's error
    constructor signature (which has changed across versions).
    """

    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("fake rate limit")
        self.response = _FakeResponse(headers={"retry-after": retry_after} if retry_after else {})


@dataclass
class _FakeResponse:
    headers: dict[str, str]


class _SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, msg: str) -> None:
        self.messages.append(msg)


# ---------------------------------------------------------------------------
# retry_on_rate_limit: direct helper behaviour
# ---------------------------------------------------------------------------


def test_helper_returns_result_on_first_success() -> None:
    """Happy path — no exception, no sleep, returns the value."""
    sleep = _SleepRecorder()
    result = retry_on_rate_limit(
        lambda: "answer",
        retry_exceptions=(_FakeRateLimit,),
        sleep=sleep,
        log=_LogRecorder(),
    )
    assert result == "answer"
    assert sleep.calls == []


def test_helper_retries_then_succeeds() -> None:
    """Two failures followed by success should yield the success value."""
    call_count = {"n": 0}

    def flaky() -> str:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _FakeRateLimit(retry_after="7.0")
        return "finally"

    sleep = _SleepRecorder()
    log = _LogRecorder()
    result = retry_on_rate_limit(
        flaky,
        retry_exceptions=(_FakeRateLimit,),
        sleep=sleep,
        log=log,
    )

    assert result == "finally"
    assert call_count["n"] == 3
    # Two sleeps, both honouring the 7s retry-after header.
    assert sleep.calls == [7.0, 7.0]
    assert all("retry-after header" in msg for msg in log.messages)


def test_helper_falls_back_to_exponential_backoff_without_header() -> None:
    """Without a retry-after header, sleeps should grow exponentially."""
    call_count = {"n": 0}

    def always_fail() -> str:
        call_count["n"] += 1
        raise _FakeRateLimit(retry_after=None)

    sleep = _SleepRecorder()
    with pytest.raises(_FakeRateLimit):
        retry_on_rate_limit(
            always_fail,
            retry_exceptions=(_FakeRateLimit,),
            max_attempts=4,
            base_backoff_seconds=2.0,
            max_backoff_seconds=999.0,
            sleep=sleep,
            log=_LogRecorder(),
        )

    # 4 attempts = 3 sleeps, doubling from base 2s: 2, 4, 8.
    assert sleep.calls == [2.0, 4.0, 8.0]
    assert call_count["n"] == 4


def test_helper_caps_exponential_backoff_at_max() -> None:
    """Exponential backoff must never exceed max_backoff_seconds."""

    def always_fail() -> str:
        raise _FakeRateLimit(retry_after=None)

    sleep = _SleepRecorder()
    with pytest.raises(_FakeRateLimit):
        retry_on_rate_limit(
            always_fail,
            retry_exceptions=(_FakeRateLimit,),
            max_attempts=6,
            base_backoff_seconds=10.0,
            max_backoff_seconds=20.0,
            sleep=sleep,
            log=_LogRecorder(),
        )

    # Raw progression would be 10, 20, 40, 80, 160 — cap at 20.
    assert sleep.calls == [10.0, 20.0, 20.0, 20.0, 20.0]


def test_helper_also_caps_retry_after_header() -> None:
    """A malicious / mis-set retry-after header must not block the run for hours."""

    def fail_once_with_big_header() -> str:
        raise _FakeRateLimit(retry_after="99999")

    sleep = _SleepRecorder()
    with pytest.raises(_FakeRateLimit):
        retry_on_rate_limit(
            fail_once_with_big_header,
            retry_exceptions=(_FakeRateLimit,),
            max_attempts=2,
            max_backoff_seconds=60.0,
            sleep=sleep,
            log=_LogRecorder(),
        )

    assert sleep.calls == [60.0]


def test_helper_reraises_after_max_attempts() -> None:
    """After max_attempts failures, the last exception propagates."""

    def always_fail() -> str:
        raise _FakeRateLimit(retry_after="1")

    sleep = _SleepRecorder()
    with pytest.raises(_FakeRateLimit):
        retry_on_rate_limit(
            always_fail,
            retry_exceptions=(_FakeRateLimit,),
            max_attempts=3,
            sleep=sleep,
            log=_LogRecorder(),
        )

    # 3 attempts = 2 sleeps between them.
    assert len(sleep.calls) == 2


def test_helper_does_not_retry_non_matching_exceptions() -> None:
    """Exceptions outside `retry_exceptions` must propagate immediately."""

    def raises_value_error() -> str:
        raise ValueError("unrelated")

    sleep = _SleepRecorder()
    with pytest.raises(ValueError, match="unrelated"):
        retry_on_rate_limit(
            raises_value_error,
            retry_exceptions=(_FakeRateLimit,),
            sleep=sleep,
            log=_LogRecorder(),
        )

    assert sleep.calls == []


def test_helper_rejects_max_attempts_below_one() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        retry_on_rate_limit(
            lambda: None,
            retry_exceptions=(_FakeRateLimit,),
            max_attempts=0,
        )


# ---------------------------------------------------------------------------
# Runner integration: BaselineRunner survives a transient 429
# ---------------------------------------------------------------------------


@dataclass
class _FakeContent:
    text: str


@dataclass
class _FakeMessage:
    content: list[_FakeContent]


class _FlakyMessages:
    """Fake `client.messages` that raises RateLimitError twice then succeeds."""

    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls += 1
        if self.calls <= 2:
            raise _FakeRateLimit(retry_after="0")  # 0s for fast tests
        return _FakeMessage(content=[_FakeContent(text="recovered answer")])


class _FlakyClient:
    def __init__(self) -> None:
        self.messages = _FlakyMessages()


def test_baseline_runner_recovers_from_transient_rate_limit(monkeypatch) -> None:
    """End-to-end: BaselineRunner absorbs two 429s and returns the final answer."""
    # Patch the exception-class resolver so the runner retries our fake class
    # without needing the real anthropic SDK installed.
    import headroom.evals.runners.direct_runners as direct_runners

    monkeypatch.setattr(
        direct_runners,
        "_anthropic_rate_limit_exceptions",
        lambda: (_FakeRateLimit,),
    )
    # Make the retry sleeps instant so the test stays fast.
    monkeypatch.setattr(
        "headroom.evals.runners._rate_limit.time.sleep",
        lambda _s: None,
    )

    # Minimal LongMemEval-shaped case so _flatten_haystack can parse it.
    context = json.dumps({"haystack_sessions": [[{"role": "user", "content": "hi"}]]})
    case = EvalCase(
        id="test-case",
        context=context,
        query="what did I say?",
        ground_truth="hi",
    )

    client = _FlakyClient()
    runner = BaselineRunner(
        client=client,
        provider="anthropic",
        model="claude-sonnet-4-5-20250929",
        max_tokens=32,
    )

    result = runner.run(case)

    assert result.error is None
    assert result.answer == "recovered answer"
    assert client.messages.calls == 3  # two failures + one success
