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


LONGBENCH_V1_TASKS_EXPECTED = [
    "narrativeqa",
    "qasper",
    "multifieldqa_en",
    "hotpotqa",
    "2wikimqa",
    "musique",
    "gov_report",
    "qmsum",
    "multi_news",
    "trec",
    "triviaqa",
    "samsum",
    "passage_count",
    "passage_retrieval_en",
    "lcc",
    "repobench-p",
]


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


class TestLoadLongBenchV1Suite:
    def test_returns_suite_covering_all_llmlingua2_tasks(self, patch_hf_load_dataset_longbench):
        from headroom.evals.datasets import LONGBENCH_V1_TASKS, load_longbench_v1_suite

        # Constant must match the LLMLingua-2 reported task list exactly.
        assert LONGBENCH_V1_TASKS == LONGBENCH_V1_TASKS_EXPECTED

        suite = load_longbench_v1_suite(n_per_task=2)

        # The fixture has 3 rows; n_per_task=2 → 2 cases per task × 16 tasks = 32.
        assert suite.name == "LongBench_v1_suite"
        assert len(suite.cases) == len(LONGBENCH_V1_TASKS_EXPECTED) * 2

    def test_case_metadata_includes_task_name(self, patch_hf_load_dataset_longbench):
        from headroom.evals.datasets import load_longbench_v1_suite

        suite = load_longbench_v1_suite(n_per_task=1)
        tasks_seen = {c.metadata["task"] for c in suite.cases}

        assert tasks_seen == set(LONGBENCH_V1_TASKS_EXPECTED)

    def test_case_id_is_prefixed_by_task(self, patch_hf_load_dataset_longbench):
        from headroom.evals.datasets import load_longbench_v1_suite

        suite = load_longbench_v1_suite(n_per_task=1)
        for case in suite.cases:
            assert case.id.startswith(f"longbench_{case.metadata['task']}_")

    def test_registry_entry(self, patch_hf_load_dataset_longbench):
        from headroom.evals.datasets import DATASET_REGISTRY, load_dataset_by_name

        assert "longbench_v1_suite" in DATASET_REGISTRY
        assert DATASET_REGISTRY["longbench_v1_suite"]["category"] == "long_context"

        suite = load_dataset_by_name("longbench_v1_suite", n_per_task=1)
        assert len(suite.cases) == len(LONGBENCH_V1_TASKS_EXPECTED)


@pytest.mark.integration
class TestRealHuggingFaceLoading:
    """Smoke tests that hit the real HuggingFace Hub. Skipped by default.

    Run with:
        pytest tests/test_evals/test_dataset_loaders.py -m integration -v
    """

    def test_nemotron_agentic_v1_real_load(self):
        pytest.importorskip("datasets")
        from headroom.evals.datasets import load_nemotron_agentic_v1

        suite = load_nemotron_agentic_v1(n=2, split="interactive_agent")

        assert len(suite.cases) == 2
        for case in suite.cases:
            assert case.context  # non-empty
            assert case.metadata["source"] == "Nemotron-Agentic-v1"
            assert case.metadata["num_messages"] >= 1

    def test_longbench_v1_suite_real_load_single_task(self):
        pytest.importorskip("datasets")
        from headroom.evals.datasets import load_longbench_v1_suite

        # Only load narrativeqa to keep the download small.
        suite = load_longbench_v1_suite(n_per_task=2, tasks=["narrativeqa"])

        assert len(suite.cases) == 2
        for case in suite.cases:
            assert case.context
            assert case.metadata["task"] == "narrativeqa"


class TestDatasetRegistryWiring:
    def test_list_available_datasets_includes_both(self):
        from headroom.evals.datasets import list_available_datasets

        by_category = list_available_datasets()

        assert "nemotron_agentic_v1" in by_category["tool_use"]
        assert "longbench_v1_suite" in by_category["long_context"]

    def test_load_dataset_by_name_nemotron(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_dataset_by_name

        suite = load_dataset_by_name("nemotron_agentic_v1", n=2)
        assert suite.name.startswith("Nemotron-Agentic-v1_")
        assert len(suite.cases) == 2

    def test_load_dataset_by_name_longbench_v1_suite(self, patch_hf_load_dataset_longbench):
        from headroom.evals.datasets import load_dataset_by_name

        suite = load_dataset_by_name("longbench_v1_suite", n_per_task=1)
        assert suite.name == "LongBench_v1_suite"
        assert len(suite.cases) == 16  # one per task

    def test_unknown_dataset_raises_with_helpful_error(self):
        from headroom.evals.datasets import load_dataset_by_name

        with pytest.raises(ValueError, match="Unknown dataset"):
            load_dataset_by_name("does_not_exist")
