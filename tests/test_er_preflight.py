"""Tests for ER README pre-flight (tools/orchestrator/er_preflight.py).

The LLM call is faked via complete_fn; the decision tree is exercised
directly through _decide and end-to-end through assess_readme.
"""

from __future__ import annotations

import json

from tools.orchestrator.er_preflight import (
    FLAG_MISSING_INTERMEDIATE,
    FLAG_MISSING_README,
    FLAG_MISSING_RUNTIME,
    MODE_FULL_RUN,
    MODE_SKIP_NO_INTERMEDIATE,
    MODE_SKIP_NO_README,
    MODE_SKIP_NO_RUNTIME,
    MODE_SPOT_CHECK,
    _coerce_assessment,
    _decide,
    assess_readme,
    find_readme,
)
from tools.orchestrator.llm import LLMResponse

BUDGET = 3 * 60 * 60  # 3 hours


def _fake(text: str):
    def backend(model, messages, tools):
        return LLMResponse(text=text)
    return backend


def _assess(**overrides):
    base = {
        "runtime_documented": True,
        "estimated_seconds": 60,
        "runtime_is_open_ended": False,
        "intermediate_results_documented": False,
        "checkpoint_scripts": [],
        "rationale": "x",
    }
    base.update(overrides)
    return base


# ---- find_readme -----------------------------------------------------------

def test_find_readme_prefers_markdown(tmp_path):
    (tmp_path / "README.md").write_text("# hi")
    (tmp_path / "README.txt").write_text("hi")
    assert find_readme(tmp_path).name == "README.md"


def test_find_readme_case_insensitive(tmp_path):
    (tmp_path / "readme.MD").write_text("# hi")
    found = find_readme(tmp_path)
    assert found is not None and found.name.lower() == "readme.md"


def test_find_readme_none_when_absent(tmp_path):
    (tmp_path / "main.R").write_text("x <- 1")
    assert find_readme(tmp_path) is None


# ---- decision tree (_decide) ----------------------------------------------

def test_decide_no_runtime_docs_flags_major():
    out = _decide(_assess(runtime_documented=False), BUDGET)
    assert out.execution_mode == MODE_SKIP_NO_RUNTIME
    assert FLAG_MISSING_RUNTIME in out.checklist_flags
    assert not out.will_execute


def test_decide_within_budget_full_run():
    out = _decide(_assess(estimated_seconds=120), BUDGET)
    assert out.execution_mode == MODE_FULL_RUN
    assert out.will_execute
    assert out.checklist_flags == []


def test_decide_over_budget_with_intermediates_spot_check():
    out = _decide(
        _assess(
            estimated_seconds=BUDGET * 10,
            intermediate_results_documented=True,
            checkpoint_scripts=["simulate.R"],
        ),
        BUDGET,
    )
    assert out.execution_mode == MODE_SPOT_CHECK
    assert out.will_execute
    assert out.checkpoint_scripts == ["simulate.R"]


def test_decide_over_budget_no_intermediates_flags_major():
    out = _decide(
        _assess(estimated_seconds=BUDGET * 10, intermediate_results_documented=False),
        BUDGET,
    )
    assert out.execution_mode == MODE_SKIP_NO_INTERMEDIATE
    assert FLAG_MISSING_INTERMEDIATE in out.checklist_flags
    assert not out.will_execute


def test_decide_open_ended_runtime_exceeds_budget():
    # Open-ended ("several days") with null estimate still counts as over budget.
    out = _decide(
        _assess(
            estimated_seconds=None,
            runtime_is_open_ended=True,
            intermediate_results_documented=False,
        ),
        BUDGET,
    )
    assert out.execution_mode == MODE_SKIP_NO_INTERMEDIATE


def test_decide_narrative_without_number_fits_budget():
    # "runs quickly" -> documented true, estimate null, not open-ended -> full run.
    out = _decide(
        _assess(estimated_seconds=None, runtime_is_open_ended=False),
        BUDGET,
    )
    assert out.execution_mode == MODE_FULL_RUN


# ---- _coerce_assessment ----------------------------------------------------

def test_coerce_handles_string_seconds():
    out = _coerce_assessment({"runtime_documented": True, "estimated_seconds": "300"})
    assert out["estimated_seconds"] == 300


def test_coerce_handles_garbage_seconds():
    out = _coerce_assessment({"runtime_documented": True, "estimated_seconds": "soon"})
    assert out["estimated_seconds"] is None


def test_coerce_filters_non_string_scripts():
    out = _coerce_assessment({"checkpoint_scripts": ["a.R", 5, None, "b.R"]})
    assert out["checkpoint_scripts"] == ["a.R", "b.R"]


# ---- assess_readme end to end ---------------------------------------------

def test_assess_readme_no_readme_skips(tmp_path):
    (tmp_path / "main.R").write_text("x <- 1")
    out = assess_readme(tmp_path, budget_seconds=BUDGET, complete_fn=_fake("{}"))
    assert out.execution_mode == MODE_SKIP_NO_README
    assert FLAG_MISSING_README in out.checklist_flags
    assert out.readme_found is False


def test_assess_readme_full_run(tmp_path):
    (tmp_path / "README.md").write_text("Run main.R. Takes about 2 minutes.")
    payload = json.dumps({
        "runtime_documented": True,
        "estimated_seconds": 120,
        "runtime_is_open_ended": False,
        "intermediate_results_documented": False,
        "checkpoint_scripts": [],
        "rationale": "2 minutes stated",
    })
    out = assess_readme(tmp_path, budget_seconds=BUDGET, complete_fn=_fake(payload))
    assert out.execution_mode == MODE_FULL_RUN
    assert out.will_execute


def test_assess_readme_llm_failure_degrades_conservatively(tmp_path):
    (tmp_path / "README.md").write_text("Run main.R.")
    out = assess_readme(tmp_path, budget_seconds=BUDGET, complete_fn=_fake("not json"))
    assert out.execution_mode == MODE_SKIP_NO_RUNTIME
    assert FLAG_MISSING_RUNTIME in out.checklist_flags
