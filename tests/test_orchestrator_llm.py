"""Tests for the provider-agnostic orchestrator seam.

The agent loop is exercised with an injected fake completion backend and a fake
tool runner, so these tests need neither LiteLLM nor network access — the same
conditions CI runs under.
"""

from __future__ import annotations

import pytest

from tools.orchestrator.config import STAGE_MODELS, model_for
from tools.orchestrator.llm import AgentStepLimit, LLMResponse, ToolCall, run_agent


class FakeLLM:
    """A scripted completion backend that records the messages it received."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, list[dict], list]] = []

    def __call__(self, model, messages, tools):
        self.calls.append((model, [dict(m) for m in messages], list(tools)))
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def test_no_tool_calls_returns_text():
    llm = FakeLLM([LLMResponse(text="final answer")])
    out = run_agent(
        system="sys",
        user="hi",
        model="fake/model",
        complete_fn=llm,
        tool_runner=lambda *a, **k: None,
    )
    assert out == "final answer"
    assert len(llm.calls) == 1


def test_tool_call_executed_and_result_fed_back():
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[ToolCall(id="c1", name="list_files", arguments={"directory": "/x"})]
            ),
            LLMResponse(text="done"),
        ]
    )
    received: dict = {}

    def runner(name, **kwargs):
        received["name"] = name
        received["kwargs"] = kwargs
        return {"files": ["a.R"]}

    out = run_agent(
        system="sys", user="audit", model="fake/model", complete_fn=llm, tool_runner=runner
    )

    assert out == "done"
    assert received == {"name": "list_files", "kwargs": {"directory": "/x"}}

    # The second completion must have seen the assistant tool-call message
    # followed by the tool result, threaded by tool_call_id.
    second_msgs = llm.calls[1][1]
    assert second_msgs[-2]["role"] == "assistant"
    assert second_msgs[-2]["tool_calls"][0]["id"] == "c1"
    assert second_msgs[-1]["role"] == "tool"
    assert second_msgs[-1]["tool_call_id"] == "c1"
    assert "a.R" in second_msgs[-1]["content"]


def test_string_tool_result_passed_through():
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={})]),
            LLMResponse(text="ok"),
        ]
    )
    run_agent(
        system="s",
        user="u",
        model="m",
        complete_fn=llm,
        tool_runner=lambda *a, **k: "plain string",
    )
    assert llm.calls[1][1][-1]["content"] == "plain string"


def test_tool_error_is_surfaced_not_raised():
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="boom", arguments={})]),
            LLMResponse(text="recovered"),
        ]
    )

    def runner(name, **kwargs):
        raise RuntimeError("kaboom")

    out = run_agent(system="s", user="u", model="m", complete_fn=llm, tool_runner=runner)

    assert out == "recovered"
    tool_msg = llm.calls[1][1][-1]
    assert tool_msg["role"] == "tool"
    assert "kaboom" in tool_msg["content"]


def test_step_limit_raises():
    def always_tool(model, messages, tools):
        return LLMResponse(tool_calls=[ToolCall(id="c", name="noop", arguments={})])

    with pytest.raises(AgentStepLimit):
        run_agent(
            system="s",
            user="u",
            model="m",
            complete_fn=always_tool,
            tool_runner=lambda *a, **k: "ok",
            max_steps=3,
        )


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------

def test_model_for_returns_default(monkeypatch):
    monkeypatch.delenv("AI4R_MODEL_KBE", raising=False)
    assert model_for("kbe") == STAGE_MODELS["kbe"]


def test_model_for_env_override(monkeypatch):
    monkeypatch.setenv("AI4R_MODEL_KBE", "anthropic/claude-test")
    assert model_for("kbe") == "anthropic/claude-test"


def test_model_for_unknown_stage_raises(monkeypatch):
    monkeypatch.delenv("AI4R_MODEL_NOPE", raising=False)
    with pytest.raises(KeyError):
        model_for("nope")
