# HF Benchmark Datasets (Nemotron-Agentic-v1 + LongBench v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two Hugging Face dataset loaders (`nvidia/Nemotron-Agentic-v1` and `THUDM/LongBench` v1 multi-task suite) to `headroom.evals.datasets` so the 5-arm compression report can consume real agent trajectories and the canonical LLMLingua-2 comparison surface.

**Architecture:** Extend the existing `headroom/evals/datasets.py` module. It already defines `EvalCase` / `EvalSuite` types, a `DATASET_REGISTRY`, and patterns for wrapping `datasets.load_dataset(...)`. `load_longbench()` already exists as a single-task loader — we add a suite wrapper that covers the 16 LongBench v1 tasks LLMLingua-2 reports on. Nemotron-Agentic-v1 is brand new: we add `load_nemotron_agentic_v1()` that splits each trajectory at the last user turn and emits one `EvalCase` per trajectory with context=history+tools, query=last user turn, ground_truth=next assistant response.

Tests use hand-built JSON fixtures that mirror the HF schema and monkeypatch `datasets.load_dataset` so unit tests never touch the network. One network-gated smoke test verifies real HF loading.

**Tech Stack:** Python 3.10+, `datasets>=2.14.0` (already in `[evals]` extra), `pytest`, `pytest-asyncio`, ruff, mypy. No new dependencies.

**Prerequisites the engineer should know:**
- Headroom uses `uv` or `pip install -e .[dev,evals]` for local install.
- `EvalCase` fields: `id`, `context` (str), `query` (str), `ground_truth` (str|None), `metadata` (dict).
- `EvalSuite` is `name: str, cases: list[EvalCase]`.
- Tests live in `tests/test_evals/`; conftest at `tests/conftest.py` if shared fixtures needed.
- `ruff check .` and `ruff format .` must pass before commit (see `.github/workflows/ci.yml`).
- The `datasets` package is an optional dep behind the `[evals]` extra. Loaders must call `_check_datasets_installed()` before importing `datasets`.

---

## File Structure

**Modified:**
- `headroom/evals/datasets.py` — add two loaders and two registry entries.

**Created:**
- `tests/test_evals/test_dataset_loaders.py` — unit tests for both loaders, using fixtures + monkeypatched `datasets.load_dataset`.
- `tests/test_evals/fixtures/__init__.py` — empty marker.
- `tests/test_evals/fixtures/nemotron_agentic_v1_sample.json` — 3 hand-built trajectories mirroring HF schema.
- `tests/test_evals/fixtures/longbench_narrativeqa_sample.json` — 3 hand-built LongBench rows.

**Touched (documentation only):**
- `research/literature-review-datasets.md` — add "Integration status" section.

---

## Task 1: Scaffold fixtures directory

**Files:**
- Create: `tests/test_evals/fixtures/__init__.py`
- Create: `tests/test_evals/fixtures/nemotron_agentic_v1_sample.json`
- Create: `tests/test_evals/fixtures/longbench_narrativeqa_sample.json`

- [ ] **Step 1.1: Create fixtures directory marker**

Create `tests/test_evals/fixtures/__init__.py` as an empty file (so pytest discovery works cleanly).

```python
```

- [ ] **Step 1.2: Create Nemotron-Agentic-v1 fixture**

Create `tests/test_evals/fixtures/nemotron_agentic_v1_sample.json` with 3 synthetic rows that mirror the real HF schema (`uuid`, `messages`, `tools`, `license`, `used_in`, `reasoning`). One row must end with a user turn (so the loader splits at that turn), one must end with an assistant turn (so the loader uses the second-to-last user turn), and one must contain tool calls (so tool_calls serialization is exercised).

```json
[
  {
    "uuid": "fixture-001-ends-on-user",
    "messages": [
      {"role": "system", "content": "You are a food ordering assistant."},
      {"role": "user", "content": "Order a pizza from Luigi's."},
      {"role": "assistant", "content": "Sure, what size and toppings?"},
      {"role": "user", "content": "Large, pepperoni and mushrooms."}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "place_order",
          "description": "Place a food delivery order",
          "parameters": {"type": "object", "properties": {"restaurant": {"type": "string"}, "items": {"type": "array"}}}
        }
      }
    ],
    "license": "cc-by-4.0",
    "used_in": ["nano_v3"],
    "reasoning": "User wants a pizza order."
  },
  {
    "uuid": "fixture-002-ends-on-assistant",
    "messages": [
      {"role": "system", "content": "You are a weather assistant."},
      {"role": "user", "content": "What's the weather in Tokyo?"},
      {"role": "assistant", "content": "It's 18C and sunny in Tokyo today."}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get current weather for a city",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
        }
      }
    ],
    "license": "cc-by-4.0",
    "used_in": ["nano_v3"],
    "reasoning": "Simple weather lookup."
  },
  {
    "uuid": "fixture-003-with-tool-calls",
    "messages": [
      {"role": "system", "content": "You are a calculator assistant."},
      {"role": "user", "content": "What is 15 * 23?"},
      {"role": "assistant", "content": "Let me calculate that.", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "multiply", "arguments": "{\"a\": 15, \"b\": 23}"}}]},
      {"role": "tool", "tool_call_id": "call_1", "content": "345"},
      {"role": "assistant", "content": "15 * 23 = 345."}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "multiply",
          "description": "Multiply two numbers",
          "parameters": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}}
        }
      }
    ],
    "license": "cc-by-4.0",
    "used_in": ["nano_v3"],
    "reasoning": "Arithmetic via tool call."
  }
]
```

- [ ] **Step 1.3: Create LongBench fixture**

Create `tests/test_evals/fixtures/longbench_narrativeqa_sample.json` with 3 rows mirroring the real `THUDM/LongBench` schema (fields `context`, `input`, `answers`, `length`, `dataset`, `language`, `all_classes`, `_id`).

```json
[
  {
    "_id": "fix-lb-001",
    "dataset": "narrativeqa",
    "language": "en",
    "context": "Alice walked into the forest on a crisp autumn morning. She had packed a small lunch and was looking forward to a long hike.",
    "input": "What season was it when Alice walked into the forest?",
    "answers": ["autumn"],
    "length": 20,
    "all_classes": []
  },
  {
    "_id": "fix-lb-002",
    "dataset": "narrativeqa",
    "language": "en",
    "context": "The detective examined the room carefully. A broken vase lay on the floor and the window was wide open.",
    "input": "What was broken in the room?",
    "answers": ["the vase", "a vase"],
    "length": 18,
    "all_classes": []
  },
  {
    "_id": "fix-lb-003",
    "dataset": "narrativeqa",
    "language": "en",
    "context": "The spaceship approached Mars at dawn. Captain Vega ordered the crew to begin descent procedures.",
    "input": "Who ordered the descent?",
    "answers": ["Captain Vega"],
    "length": 15,
    "all_classes": []
  }
]
```

- [ ] **Step 1.4: Commit fixtures**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
git add tests/test_evals/fixtures/__init__.py tests/test_evals/fixtures/nemotron_agentic_v1_sample.json tests/test_evals/fixtures/longbench_narrativeqa_sample.json
git commit -m "test(evals): add fixtures for HF dataset loader tests"
```

---

## Task 2: TDD load_nemotron_agentic_v1

**Files:**
- Create: `tests/test_evals/test_dataset_loaders.py`
- Modify: `headroom/evals/datasets.py` (add `load_nemotron_agentic_v1` + registry entry)

- [ ] **Step 2.1: Write the failing unit test**

Create `tests/test_evals/test_dataset_loaders.py` with a test that loads the fixture through `load_nemotron_agentic_v1`, monkeypatching `datasets.load_dataset` to return the fixture rows. The test must assert on concrete behavior: the three fixture rows produce three `EvalCase` objects, the `context` contains the tool definitions + prior messages, the `query` is the last user turn when the trajectory ends on user, and the `ground_truth` is the last assistant response when the trajectory ends on assistant.

```python
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
        case = next(
            c for c in suite.cases if c.id == "nemotron_fixture-002-ends-on-assistant"
        )

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
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py::TestLoadNemotronAgenticV1 -v
```

Expected: **FAIL** with `ImportError: cannot import name 'load_nemotron_agentic_v1' from 'headroom.evals.datasets'`.

- [ ] **Step 2.3: Implement load_nemotron_agentic_v1**

Add the following function to `headroom/evals/datasets.py`. Place it in the "TOOL USE / FUNCTION CALLING DATASETS" section (after `load_bfcl` is a fine spot — use `grep -n "def load_bfcl" headroom/evals/datasets.py` to find the insertion point). The function splits each trajectory at the last user turn: everything before and including that user turn becomes the context (plus the tools schema), the user turn text becomes the query, and the next assistant message (if any) becomes the ground truth.

```python
def load_nemotron_agentic_v1(
    n: int = 100,
    split: str = "interactive_agent",
) -> EvalSuite:
    """Load NVIDIA Nemotron-Agentic-v1 multi-turn tool-use trajectories.

    Each trajectory is a synthetic multi-turn conversation where an agent
    reasons, calls tools, and responds to tool output. The loader splits
    each trajectory at the last user turn:

    - context: JSON-serialized {tools, prior_messages} — what Headroom compresses
    - query: text of the last user message
    - ground_truth: text of the assistant's response that follows (if any)

    Dataset: https://huggingface.co/datasets/nvidia/Nemotron-Agentic-v1
    License: CC BY 4.0 (commercial use permitted).

    Args:
        n: Number of trajectories to load.
        split: Dataset split — "interactive_agent" (19k) or "tool_calling" (316k).

    Returns:
        EvalSuite with one EvalCase per trajectory.
    """
    _check_datasets_installed()
    from datasets import load_dataset

    ds = load_dataset("nvidia/Nemotron-Agentic-v1", split=split)

    cases: list[EvalCase] = []
    for i, item in enumerate(ds):
        if len(cases) >= n:
            break

        messages = item.get("messages") or []
        tools = item.get("tools") or []
        uuid = item.get("uuid") or f"nemotron_{i}"

        if not messages:
            continue

        # Find the index of the last user turn.
        last_user_idx = None
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].get("role") == "user":
                last_user_idx = idx
                break

        if last_user_idx is None:
            continue  # No user turn — skip

        prior = messages[:last_user_idx]  # everything before the last user turn
        last_user = messages[last_user_idx]
        after = messages[last_user_idx + 1 :]

        # ground_truth = first assistant message after the last user turn, if any
        ground_truth: str | None = None
        for msg in after:
            if msg.get("role") == "assistant":
                # Prefer content; fall back to JSON of the whole message for tool_calls
                content = msg.get("content")
                if content:
                    ground_truth = content
                else:
                    ground_truth = json.dumps(msg, ensure_ascii=False)
                break

        # context = JSON of {tools, messages_up_to_and_including_last_user}
        context_obj = {
            "tools": tools,
            "messages": prior + [last_user],
        }
        context = json.dumps(context_obj, ensure_ascii=False, indent=2)

        query = last_user.get("content") or ""

        cases.append(
            EvalCase(
                id=f"nemotron_{uuid}",
                context=context,
                query=query,
                ground_truth=ground_truth,
                metadata={
                    "source": "Nemotron-Agentic-v1",
                    "split": split,
                    "num_messages": len(messages),
                    "num_tools": len(tools) if isinstance(tools, list) else 0,
                    "license": item.get("license", "cc-by-4.0"),
                },
            )
        )

    return EvalSuite(name=f"Nemotron-Agentic-v1_{split}", cases=cases)
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py::TestLoadNemotronAgenticV1 -v
```

Expected: **PASS** — all 7 tests green.

- [ ] **Step 2.5: Register in DATASET_REGISTRY**

Open `headroom/evals/datasets.py`, find the `DATASET_REGISTRY` dict (near the bottom of the file, in the "DATASET REGISTRY & UTILITIES" section), and add a `nemotron_agentic_v1` entry inside the "Tool Use" block (after the `toolbench` entry).

```python
    "nemotron_agentic_v1": {
        "loader": load_nemotron_agentic_v1,
        "description": "NVIDIA Nemotron-Agentic-v1 — multi-turn synthetic tool-use trajectories (CC-BY-4.0)",
        "category": "tool_use",
        "default_n": 100,
    },
```

- [ ] **Step 2.6: Add a registry lookup test**

Append this test class to `tests/test_evals/test_dataset_loaders.py`.

```python
class TestNemotronRegistry:
    def test_listed_in_registry(self):
        from headroom.evals.datasets import DATASET_REGISTRY

        assert "nemotron_agentic_v1" in DATASET_REGISTRY
        assert DATASET_REGISTRY["nemotron_agentic_v1"]["category"] == "tool_use"

    def test_load_dataset_by_name(self, patch_hf_load_dataset_nemotron):
        from headroom.evals.datasets import load_dataset_by_name

        suite = load_dataset_by_name("nemotron_agentic_v1", n=10)
        assert len(suite.cases) == 3
```

- [ ] **Step 2.7: Run the new tests**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py -v
```

Expected: **PASS** — all tests (including the two registry tests) green.

- [ ] **Step 2.8: Lint and type-check**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
ruff check headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py
ruff format --check headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py
```

If `ruff format --check` fails, run `ruff format headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py` and re-run the check.

- [ ] **Step 2.9: Commit**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
git add headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py
git commit -m "feat(evals): add Nemotron-Agentic-v1 dataset loader

Adds load_nemotron_agentic_v1() that wraps nvidia/Nemotron-Agentic-v1 HF
dataset. Each trajectory is split at the last user turn: tools + prior
messages become the context, the user turn is the query, the next
assistant message is the ground_truth. Registered in DATASET_REGISTRY
under the tool_use category."
```

---

## Task 3: TDD load_longbench_v1_suite (multi-task convenience loader)

`load_longbench()` already exists and loads a single task. For the 5-arm report we need to run across the 16 LongBench v1 tasks LLMLingua-2 reports on. Add a thin wrapper that concatenates cases from multiple tasks into one `EvalSuite`, tagged by source task.

**Files:**
- Modify: `headroom/evals/datasets.py` (add `load_longbench_v1_suite` + registry entry)
- Modify: `tests/test_evals/test_dataset_loaders.py` (add test class)

- [ ] **Step 3.1: Write the failing unit test**

Append this test class to `tests/test_evals/test_dataset_loaders.py`.

```python
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


class TestLoadLongBenchV1Suite:
    def test_returns_suite_covering_all_llmlingua2_tasks(
        self, patch_hf_load_dataset_longbench
    ):
        from headroom.evals.datasets import LONGBENCH_V1_TASKS, load_longbench_v1_suite

        # Constant must match the LLMLingua-2 reported task list exactly.
        assert LONGBENCH_V1_TASKS == LONGBENCH_V1_TASKS_EXPECTED

        suite = load_longbench_v1_suite(n_per_task=2)

        # 2 cases per task * 16 tasks = 32, but the fixture only has 3 rows,
        # so each task yields min(2, 3) = 2 cases → 32 total.
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
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py::TestLoadLongBenchV1Suite -v
```

Expected: **FAIL** with `ImportError: cannot import name 'LONGBENCH_V1_TASKS' from 'headroom.evals.datasets'`.

- [ ] **Step 3.3: Implement LONGBENCH_V1_TASKS and load_longbench_v1_suite**

Open `headroom/evals/datasets.py`. Add the task constant and the suite loader right after the existing `load_longbench()` function (search for `def load_longbench(` to find the insertion point).

```python
# LLMLingua-2 reports on these 16 LongBench v1 tasks. Keep this list in sync
# with the LLMLingua-2 paper (Pan et al., 2024) Table 3 so head-to-head
# comparisons stay apples-to-apples.
LONGBENCH_V1_TASKS: list[str] = [
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


def load_longbench_v1_suite(
    n_per_task: int = 50,
    tasks: list[str] | None = None,
) -> EvalSuite:
    """Load multiple LongBench v1 tasks into one EvalSuite.

    This is the canonical LLMLingua-2 comparison surface: by default it
    covers the 16 tasks LLMLingua-2 reports on, so Headroom numbers can be
    plotted head-to-head against published prompt-compression baselines.

    Each underlying task is loaded via ``load_longbench(task, n=n_per_task)``
    and the resulting cases are concatenated. Case metadata records the
    source task name so per-task breakdowns remain possible.

    Dataset: https://huggingface.co/datasets/THUDM/LongBench

    Args:
        n_per_task: Number of samples to load from each task.
        tasks: Optional explicit task list. Defaults to LONGBENCH_V1_TASKS.

    Returns:
        EvalSuite named ``"LongBench_v1_suite"`` with all cases concatenated.
    """
    task_list = tasks if tasks is not None else LONGBENCH_V1_TASKS

    all_cases: list[EvalCase] = []
    for task in task_list:
        try:
            task_suite = load_longbench(n=n_per_task, task=task)
        except ValueError:
            # A single task failing to load must not kill the whole suite.
            continue
        all_cases.extend(task_suite.cases)

    return EvalSuite(name="LongBench_v1_suite", cases=all_cases)
```

- [ ] **Step 3.4: Register in DATASET_REGISTRY**

Add this entry to `DATASET_REGISTRY` in the "Long Context" block, right after the existing `"longbench"` entry.

```python
    "longbench_v1_suite": {
        "loader": load_longbench_v1_suite,
        "description": "LongBench v1 — 16-task suite for LLMLingua-2 head-to-head comparisons",
        "category": "long_context",
        "default_n": None,  # Uses n_per_task instead
    },
```

Note: `load_longbench_v1_suite` takes `n_per_task`, not `n`. The existing `load_dataset_by_name` passes `n=<value>` as a kwarg when `n` is provided. To keep the registry happy, set `default_n` to `None` and let callers pass `n_per_task` explicitly via `**kwargs`. This already works because `load_dataset_by_name` forwards `**kwargs`:

```python
# From the existing load_dataset_by_name — no change needed, just verify.
if n is not None:
    result: EvalSuite = loader(n=n, **kwargs)
else:
    result = loader(**kwargs)
```

When `default_n=None` and the caller passes no `n`, the `else` branch fires and `n_per_task` comes through via `**kwargs`. Verified by the registry test in Step 3.1.

- [ ] **Step 3.5: Run the tests**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py::TestLoadLongBenchV1Suite -v
```

Expected: **PASS** — all 4 tests green.

- [ ] **Step 3.6: Run the full dataset loader test file**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py -v
```

Expected: **PASS** — all tests from Tasks 2 and 3 green.

- [ ] **Step 3.7: Lint**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
ruff check headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py
ruff format --check headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py
```

- [ ] **Step 3.8: Commit**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
git add headroom/evals/datasets.py tests/test_evals/test_dataset_loaders.py
git commit -m "feat(evals): add LongBench v1 multi-task suite loader

Adds LONGBENCH_V1_TASKS constant (16 tasks matching LLMLingua-2 paper)
and load_longbench_v1_suite() that concatenates cases from every task
into a single EvalSuite. Enables head-to-head compression comparisons
against published LLMLingua-2 baselines. Registered as
longbench_v1_suite in DATASET_REGISTRY."
```

---

## Task 4: Network-gated integration smoke test

Unit tests above never hit HF. Add one integration test that actually downloads a tiny slice of both real datasets, guarded by a pytest marker so CI skips it by default.

**Files:**
- Modify: `pyproject.toml` (register the `integration` marker)
- Modify: `tests/test_evals/test_dataset_loaders.py` (add smoke test class)

- [ ] **Step 4.1: Register the `integration` marker**

Open `pyproject.toml`, find the `[tool.pytest.ini_options]` section, and add a `markers` entry. The current section is:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
asyncio_mode = "auto"
```

Modify it to:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short -m 'not integration'"
asyncio_mode = "auto"
markers = [
    "integration: tests that hit external networks/services (skipped by default; run with -m integration)",
]
```

The `-m 'not integration'` in `addopts` ensures plain `pytest` never runs these; `pytest -m integration` explicitly enables them.

- [ ] **Step 4.2: Write the integration smoke test**

Append this class to `tests/test_evals/test_dataset_loaders.py`.

```python
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
```

- [ ] **Step 4.3: Verify unit tests still skip the integration class**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py -v
```

Expected: **PASS**, and the output should show `2 deselected` (the two integration tests).

- [ ] **Step 4.4: Manually run the integration tests once**

This hits the network — run locally, not in CI.

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py::TestRealHuggingFaceLoading -m integration -v
```

Expected: **PASS**. Both real datasets load and the basic assertions hold. If the Nemotron dataset viewer issue causes a DatasetGenerationError at load time, fall back to `split="tool_calling"` in the test (update the test and re-run). Record which split worked in the commit message.

- [ ] **Step 4.5: Commit**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
git add pyproject.toml tests/test_evals/test_dataset_loaders.py
git commit -m "test(evals): add network-gated integration smoke tests for HF loaders

Registers an 'integration' pytest marker (skipped by default via addopts)
and adds smoke tests that hit the real nvidia/Nemotron-Agentic-v1 and
THUDM/LongBench datasets. Run locally with 'pytest -m integration'."
```

---

## Task 5: Wire into benchmark CLI entry point

Confirm the new loaders are reachable through the existing `load_dataset_by_name` API (the natural entry point for the benchmark runner) and that `list_available_datasets()` surfaces them.

**Files:**
- Modify: `tests/test_evals/test_dataset_loaders.py` (add integration-with-existing-API tests)

- [ ] **Step 5.1: Write the wiring tests**

Append this class to `tests/test_evals/test_dataset_loaders.py`.

```python
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

    def test_load_dataset_by_name_longbench_v1_suite(
        self, patch_hf_load_dataset_longbench
    ):
        from headroom.evals.datasets import load_dataset_by_name

        suite = load_dataset_by_name("longbench_v1_suite", n_per_task=1)
        assert suite.name == "LongBench_v1_suite"
        assert len(suite.cases) == 16  # one per task

    def test_unknown_dataset_raises_with_helpful_error(self):
        from headroom.evals.datasets import load_dataset_by_name

        with pytest.raises(ValueError, match="Unknown dataset"):
            load_dataset_by_name("does_not_exist")
```

- [ ] **Step 5.2: Run the wiring tests**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py::TestDatasetRegistryWiring -v
```

Expected: **PASS** — all 4 tests green.

- [ ] **Step 5.3: Run the full test file one more time to confirm nothing regressed**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
pytest tests/test_evals/test_dataset_loaders.py -v
```

Expected: **PASS** for unit tests, **deselect** for integration tests.

- [ ] **Step 5.4: Commit**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
git add tests/test_evals/test_dataset_loaders.py
git commit -m "test(evals): verify new HF loaders are wired through load_dataset_by_name"
```

---

## Task 6: Update research doc with integration status

- [ ] **Step 6.1: Append an integration-status section to the research doc**

Open `research/literature-review-datasets.md`. At the very end of the file, after the "Sources" section, append the following block verbatim.

```markdown

---

## Integration status (2026-04-08)

Both picks are now loadable via `headroom.evals.datasets`:

```python
from headroom.evals.datasets import load_dataset_by_name

# Nemotron-Agentic-v1 (tool-use modality gap)
nemotron = load_dataset_by_name("nemotron_agentic_v1", n=200)

# LongBench v1 multi-task suite (LLMLingua-2 head-to-head)
longbench = load_dataset_by_name("longbench_v1_suite", n_per_task=50)
```

Registered names:
- `nemotron_agentic_v1` (category: `tool_use`) — wraps `nvidia/Nemotron-Agentic-v1`,
  splits each trajectory at the last user turn into `(context, query, ground_truth)`.
- `longbench_v1_suite` (category: `long_context`) — concatenates the 16
  LongBench v1 tasks from the LLMLingua-2 paper into a single EvalSuite with
  per-case `metadata["task"]` so breakdowns remain possible.

Tests: `tests/test_evals/test_dataset_loaders.py`
- Unit tests use hand-built fixtures + monkeypatched `datasets.load_dataset`.
- Integration smoke tests are guarded by `@pytest.mark.integration` and skipped
  by default. Run locally with `pytest -m integration`.
```

- [ ] **Step 6.2: Verify the markdown renders cleanly**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
tail -40 research/literature-review-datasets.md
```

Expected: the appended section is present and the surrounding sources list is intact.

- [ ] **Step 6.3: Commit**

```bash
cd /Users/arian/Developer/workspace/opensource/headroom
git add research/literature-review-datasets.md
git commit -m "docs(research): document HF dataset loader integration status"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Nemotron-Agentic-v1 loader (Task 2)
- [x] LongBench v1 multi-task loader for LLMLingua-2 comparability (Task 3)
- [x] Registry integration so benchmark runners can select them by name (Tasks 2.5, 3.4, 5)
- [x] Unit tests that never touch the network (Tasks 2, 3, fixtures in Task 1)
- [x] Network-gated integration smoke test (Task 4)
- [x] Docs updated to reflect integration status (Task 6)

**Placeholder scan:** none. Every code block contains real code; every command is runnable.

**Type consistency:**
- `load_nemotron_agentic_v1(n: int, split: str) -> EvalSuite` — used in tests and registry.
- `load_longbench_v1_suite(n_per_task: int, tasks: list[str] | None) -> EvalSuite` — used in tests, registry, and integration smoke test.
- `LONGBENCH_V1_TASKS: list[str]` — referenced by the suite loader and the unit test.
- `EvalCase.metadata["task"]` — produced by `load_longbench()` (which `load_longbench_v1_suite` delegates to) and asserted in Task 3 tests. Verified by reading `load_longbench` in `headroom/evals/datasets.py:425-434` — it sets `metadata={"source": "LongBench", "task": task, "context_length": len(context)}`.

**Gotcha flagged in Task 4.4:** the HF dataset viewer for Nemotron-Agentic-v1 is reportedly broken; if `interactive_agent` split fails at download time, the engineer is told to fall back to `tool_calling`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-08-hf-benchmark-datasets.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
