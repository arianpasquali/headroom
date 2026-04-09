"""Multi-arm driver for LongMemEval cross-arm comparisons.

CompactionCompareDriver orchestrates a sweep of an EvalSuite across multiple
arms (baseline, headroom_default, anthropic_compact, openai_compact,
summary_prompt). Each arm produces a CompactionResult per case.
Quality scoring is NOT performed here — it's the report card's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from headroom.evals.core import EvalSuite
from headroom.evals.runners.provider_compaction import CompactionResult

ArmName = Literal[
    "baseline",
    "headroom_default",
    "anthropic_compact",
    "anthropic_compact_v2",
    "anthropic_session_memory",
    "openai_compact",
    "summary_prompt",
]

_VALID_ARMS: frozenset[str] = frozenset(
    [
        "baseline",
        "headroom_default",
        "anthropic_compact",
        "anthropic_compact_v2",
        "anthropic_session_memory",
        "openai_compact",
        "summary_prompt",
    ]
)


@dataclass
class CompactionCompareConfig:
    """Configuration for one cross-arm sweep."""

    arms: list[ArmName]
    provider: Literal["anthropic", "openai"]
    model: str
    summary_model: str = "claude-haiku-4-5"
    max_tokens: int = 1024
    threshold: int = 50_000
    chunk_token_size: int = 10_000
    trigger_fill: float = 0.70
    keep_recent: int = 4
    min_turn: int = 3
    max_cycles: int = 3
    model_context_window: int = 200_000
    # --- Anthropic compact_20260112 knobs (only used by anthropic_compact_v2) ---
    compact_v2_trigger_input_tokens: int = 60_000
    compact_v2_max_tokens: int = 2048
    # --- Session memory cookbook knobs (only used by anthropic_session_memory) ---
    session_memory_answer_model: str | None = None  # None → use cfg.model
    session_memory_summary_model: str = "claude-haiku-4-5-20251001"
    session_memory_max_summary_tokens: int = 2048
    session_memory_max_answer_tokens: int = 512


@dataclass
class CompactionCompareReport:
    """Aggregate result of running an EvalSuite across multiple arms."""

    suite_name: str
    config: CompactionCompareConfig
    # Keyed by arm name → list of CompactionResult (one per case, in suite order)
    results: dict[str, list[CompactionResult]] = field(default_factory=dict)
    # Errors keyed by (arm, case_id) → error string
    errors: dict[tuple[str, str], str] = field(default_factory=dict)


class CompactionCompareDriver:
    """Orchestrates a multi-arm sweep across an EvalSuite.

    Given an EvalSuite (e.g. LongMemEval) and a CompactionCompareConfig
    listing the arms to run, dispatches each case through each requested
    arm and collects all results into a CompactionCompareReport.

    Quality scoring is NOT performed here — it's the report card's job.
    The driver only produces raw run records (answer, tokens, latency).
    """

    def __init__(
        self,
        config: CompactionCompareConfig,
        anthropic_client: object = None,
        openai_client: object = None,
    ) -> None:
        self._config = config
        self._anthropic_client = anthropic_client
        self._openai_client = openai_client

        # --- Validate arm names ---
        for arm in config.arms:
            if arm not in _VALID_ARMS:
                raise ValueError(f"Unknown arm {arm!r}. Valid arms: {sorted(_VALID_ARMS)}")

        # --- Validate provider/arm compatibility ---
        if "openai_compact" in config.arms and config.provider != "openai":
            raise ValueError(
                f"'openai_compact' arm requires provider='openai', but provider={config.provider!r}"
            )
        if "anthropic_compact" in config.arms and config.provider != "anthropic":
            raise ValueError(
                "'anthropic_compact' arm requires provider='anthropic', "
                f"but provider={config.provider!r}"
            )
        if "anthropic_compact_v2" in config.arms and config.provider != "anthropic":
            raise ValueError(
                "'anthropic_compact_v2' arm requires provider='anthropic', "
                f"but provider={config.provider!r}"
            )
        if "anthropic_session_memory" in config.arms and config.provider != "anthropic":
            raise ValueError(
                "'anthropic_session_memory' arm requires provider='anthropic', "
                f"but provider={config.provider!r}"
            )

        # --- Validate required clients ---
        _needs_anthropic = (
            config.provider == "anthropic"
            or "anthropic_compact" in config.arms
            or "anthropic_compact_v2" in config.arms
            or "anthropic_session_memory" in config.arms
            or "summary_prompt" in config.arms
        )
        if _needs_anthropic and anthropic_client is None:
            raise ValueError(
                "anthropic_client is required for the selected arms/provider "
                f"(arms={config.arms!r}, provider={config.provider!r})"
            )

        _needs_openai = config.provider == "openai" or "openai_compact" in config.arms
        if _needs_openai and openai_client is None:
            raise ValueError(
                "openai_client is required for the selected arms/provider "
                f"(arms={config.arms!r}, provider={config.provider!r})"
            )

        # --- Build runners ---
        self._runners: dict[str, Any] = {}
        provider_client = anthropic_client if config.provider == "anthropic" else openai_client

        for arm in config.arms:
            self._runners[arm] = self._build_runner(arm, provider_client)

    def _build_runner(self, arm: ArmName, provider_client: object) -> Any:
        cfg = self._config

        if arm == "baseline":
            from headroom.evals.runners.direct_runners import BaselineRunner

            return BaselineRunner(
                client=provider_client,
                provider=cfg.provider,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
            )

        if arm == "headroom_default":
            from headroom.evals.runners.direct_runners import HeadroomDefaultRunner

            return HeadroomDefaultRunner(
                client=provider_client,
                provider=cfg.provider,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
            )

        if arm == "anthropic_compact":
            from headroom.evals.runners.provider_compaction import AnthropicCompactionRunner

            return AnthropicCompactionRunner(
                client=self._anthropic_client,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                context_token_threshold=cfg.threshold,
                chunk_token_size=cfg.chunk_token_size,
            )

        if arm == "openai_compact":
            from headroom.evals.runners.provider_compaction import OpenAICompactionRunner

            return OpenAICompactionRunner(
                client=self._openai_client,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                compact_threshold=cfg.threshold,
                chunk_token_size=cfg.chunk_token_size,
            )

        if arm == "summary_prompt":
            from headroom.evals.runners.summary_prompt import SummaryPromptRunner

            return SummaryPromptRunner(
                client=self._anthropic_client,
                answer_model=cfg.model,
                summary_model=cfg.summary_model,
                model_context_window=cfg.model_context_window,
                trigger_fill=cfg.trigger_fill,
                keep_recent=cfg.keep_recent,
                min_turn=cfg.min_turn,
                max_cycles=cfg.max_cycles,
                chunk_token_size=cfg.chunk_token_size,
                max_tokens=cfg.max_tokens,
            )

        if arm == "anthropic_compact_v2":
            from headroom.evals.runners.anthropic_compact_v2 import AnthropicCompactV2Runner

            return AnthropicCompactV2Runner(
                client=self._anthropic_client,
                model=cfg.model,
                trigger_input_tokens=cfg.compact_v2_trigger_input_tokens,
                max_tokens=cfg.compact_v2_max_tokens,
            )

        if arm == "anthropic_session_memory":
            from headroom.evals.runners.anthropic_session_memory import (
                AnthropicSessionMemoryRunner,
            )

            return AnthropicSessionMemoryRunner(
                client=self._anthropic_client,
                answer_model=cfg.session_memory_answer_model or cfg.model,
                summary_model=cfg.session_memory_summary_model,
                max_summary_tokens=cfg.session_memory_max_summary_tokens,
                max_answer_tokens=cfg.session_memory_max_answer_tokens,
            )

        raise ValueError(f"Unknown arm: {arm!r}")  # should be unreachable

    def run(self, suite: EvalSuite) -> CompactionCompareReport:
        report = CompactionCompareReport(
            suite_name=suite.name,
            config=self._config,
        )

        for arm in self._config.arms:
            runner = self._runners[arm]
            arm_results: list[CompactionResult] = []

            for case in suite.cases:
                try:
                    result = runner.run(case)
                except Exception as exc:
                    error_msg = str(exc)
                    report.errors[(arm, case.id)] = error_msg
                    result = CompactionResult(
                        case_id=case.id,
                        answer="",
                        original_input_tokens=0,
                        final_input_tokens=0,
                        compression_ratio=0.0,
                        latency_ms=0.0,
                        n_iterations=0,
                        n_compactions=0,
                        error=error_msg,
                    )
                arm_results.append(result)

            report.results[arm] = arm_results

        return report
