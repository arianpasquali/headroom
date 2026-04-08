"""Tests for HuggingFace dataset loaders in headroom.evals.datasets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from headroom.evals.core import EvalCase, EvalSuite

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_nemotron_fixture() -> list[dict]:
    return json.loads((FIXTURES_DIR / "nemotron_agentic_v1_sample.json").read_text())


def _load_longbench_fixture() -> list[dict]:
    return json.loads((FIXTURES_DIR / "longbench_narrativeqa_sample.json").read_text())


class _FakeHFDataset:
    """Minimal stand-in for a HuggingFace Dataset: iterable of dicts + __len__."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


@pytest.fixture
def patch_hf_load_dataset_nemotron(monkeypatch):
    """Patch datasets.load_dataset to return the Nemotron fixture regardless of args."""
    rows = _load_nemotron_fixture()

    def fake_load_dataset(*args, **kwargs):
        return _FakeHFDataset(rows)

    import datasets as hf_datasets

    monkeypatch.setattr(hf_datasets, "load_dataset", fake_load_dataset)
    return rows


@pytest.fixture
def patch_hf_load_dataset_longbench(monkeypatch):
    rows = _load_longbench_fixture()

    def fake_load_dataset(*args, **kwargs):
        return _FakeHFDataset(rows)

    import datasets as hf_datasets

    monkeypatch.setattr(hf_datasets, "load_dataset", fake_load_dataset)
    return rows


class TestLoadNemotronAgenticV1:
    def test_returns_eval_suite_with_three_cases(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10)

        assert isinstance(suite, EvalSuite)
        assert suite.name == "Nemotron-Agentic-v1_interactive_agent"
        assert len(suite.cases) == 3
        assert all(isinstance(c, EvalCase) for c in suite.cases)

    def test_case_id_uses_uuid_from_fixture(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10)
        ids = {c.id for c in suite.cases}

        assert "nemotron_fixture-001-ends-on-user" in ids
        assert "nemotron_fixture-002-ends-on-assistant" in ids
        assert "nemotron_fixture-003-with-tool-calls" in ids

    def test_trajectory_ending_on_user_uses_last_user_as_query(
        self, patch_hf_load_dataset_nemotron
    ):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10)
        case = next(c for c in suite.cases if c.id == "nemotron_fixture-001-ends-on-user")

        assert case.query == "Large, pepperoni and mushrooms."
        assert case.ground_truth is None  # no assistant turn follows
        # Context includes tools schema and prior turns
        assert "place_order" in case.context
        assert "Order a pizza from Luigi's." in case.context

    def test_trajectory_ending_on_assistant_uses_assistant_as_ground_truth(
        self, patch_hf_load_dataset_nemotron
    ):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10)
        case = next(c for c in suite.cases if c.id == "nemotron_fixture-002-ends-on-assistant")

        assert case.query == "What's the weather in Tokyo?"
        assert case.ground_truth == "It's 18C and sunny in Tokyo today."
        assert "get_weather" in case.context

    def test_trajectory_with_tool_calls_preserves_tool_call_json(
        self, patch_hf_load_dataset_nemotron
    ):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10)
        case = next(c for c in suite.cases if c.id == "nemotron_fixture-003-with-tool-calls")

        # The tool call and tool response must appear in the serialized context
        assert "multiply" in case.context
        assert "345" in case.context

    def test_metadata_fields(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10)
        case = suite.cases[0]

        assert case.metadata["source"] == "Nemotron-Agentic-v1"
        assert case.metadata["split"] == "interactive_agent"
        assert "num_messages" in case.metadata
        assert "num_tools" in case.metadata

    def test_n_limits_number_of_cases(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=2)
        assert len(suite.cases) == 2

    def test_split_argument_affects_suite_name(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=10, split="tool_calling")
        assert suite.name == "Nemotron-Agentic-v1_tool_calling"


class TestNemotronRegistry:
    def test_listed_in_registry(self):
        from headroom.evals.datasets import DATASET_REGISTRY

        assert "nemotron_agentic_v1" in DATASET_REGISTRY
        assert DATASET_REGISTRY["nemotron_agentic_v1"]["category"] == "tool_use"

    def test_load_dataset_by_name(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_dataset_by_name

        suite = load_dataset_by_name("nemotron_agentic_v1", n=10)
        assert len(suite.cases) == 3
