"""Provider-agnostic LLM call plus the agentic tool loop.

The only LiteLLM-coupled code is :func:`_litellm_complete`, and the only
tool-registry-coupled code is the lazy import inside :func:`run_agent`.
Everything else operates on the small normalised types below, so the loop is
fully unit-testable with an injected fake backend and fake tool runner — no
network, no credentials, no heavy dependencies.

Message and tool-spec shapes follow the OpenAI Chat Completions convention,
which LiteLLM translates to each provider's native format. That keeps the
orchestrator portable across providers (and off LiteLLM entirely, if needed).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

# A tool spec in OpenAI "tools" format. Kept as a plain dict so we never couple
# to a provider's typing. Built from the tool registry in a later step.
ToolSpec = dict[str, Any]


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalised result of one completion call."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


# A completion backend: (model, messages, tools) -> LLMResponse.
CompleteFn = Callable[[str, list[dict[str, Any]], Sequence[ToolSpec]], LLMResponse]
# A tool executor: (name, **kwargs) -> Any.
ToolRunner = Callable[..., Any]


class AgentStepLimit(RuntimeError):
    """Raised when the tool loop exceeds ``max_steps`` without finishing."""


# finish_reason values that mean the model hit the output-token cap mid-answer.
_TRUNCATED_REASONS = {"length", "max_tokens", "model_length"}


class OutputTruncated(RuntimeError):
    """Raised when a final model answer was cut off at the token cap.

    Carries the partial ``text`` so callers can salvage what parsed before the
    cut, instead of silently treating a truncated answer as a parse error.
    """

    def __init__(self, text: str):
        super().__init__("model output truncated at the token limit")
        self.text = text


def _litellm_complete(
    model: str, messages: list[dict[str, Any]], tools: Sequence[ToolSpec]
) -> LLMResponse:
    """Default backend: call LiteLLM once and normalise the response.

    LiteLLM is imported here, not at module top, so importing this module — and
    unit-testing the loop with a fake backend — never requires LiteLLM.
    """
    import litellm  # lazy: only needed for real calls

    from tools.orchestrator import config

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": config.max_tokens(),
        "timeout": config.request_timeout(),
    }
    if tools:
        kwargs["tools"] = list(tools)

    # Retry in-process rather than delegating to LiteLLM's ``num_retries``: that
    # path imports ``tenacity``, a transitive dependency that — when absent —
    # crashes the call outright ("No module named 'tenacity'"), silently killing
    # a section. A small self-contained loop keeps retries working with no extra
    # dependency. (Coarse: retries any error; refine to transient-only if needed.)
    retries = config.num_retries()
    for attempt in range(retries + 1):
        try:
            response = litellm.completion(**kwargs)
            break
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(min(2 ** attempt, 8))
    message = response.choices[0].message

    calls: list[ToolCall] = []
    for tc in getattr(message, "tool_calls", None) or []:
        raw_args = tc.function.arguments
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
        calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

    finish_reason = getattr(response.choices[0], "finish_reason", None)
    return LLMResponse(text=message.content, tool_calls=calls, finish_reason=finish_reason)


def _assistant_message(resp: LLMResponse) -> dict[str, Any]:
    """Rebuild an OpenAI-format assistant message from a normalised response."""
    msg: dict[str, Any] = {"role": "assistant", "content": resp.text or ""}
    if resp.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in resp.tool_calls
        ]
    return msg


def run_agent(
    *,
    system: str,
    user: str,
    model: str,
    tools: Sequence[ToolSpec] = (),
    complete_fn: CompleteFn = _litellm_complete,
    tool_runner: ToolRunner | None = None,
    max_steps: int = 12,
) -> str:
    """Run one agent to completion and return its final text.

    Each round: call the model with the running message list; if it requested
    no tools, return its text; otherwise execute each requested tool via
    ``tool_runner``, append the results, and loop.

    ``tool_runner`` defaults to the pipeline tool registry's ``run_tool``,
    imported lazily so this module stays importable without the registry's
    runtime dependencies. Inject a fake to unit-test the loop.

    A tool that raises is reported back to the model as an error result rather
    than crashing the run, consistent with the pipeline's degraded-continuation
    philosophy (LOGIC.md §6). Raises :class:`AgentStepLimit` if ``max_steps``
    rounds pass without the model finishing.
    """
    if tool_runner is None:
        from tools.tools import run_tool

        tool_runner = run_tool

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    for _ in range(max_steps):
        resp = complete_fn(model, messages, tools)
        if not resp.tool_calls:
            if resp.finish_reason in _TRUNCATED_REASONS:
                raise OutputTruncated(resp.text or "")
            return resp.text or ""

        messages.append(_assistant_message(resp))
        for tc in resp.tool_calls:
            try:
                result = tool_runner(tc.name, **tc.arguments)
                content = result if isinstance(result, str) else json.dumps(result, default=str)
            except Exception as exc:  # surface to the model, never crash the run
                content = json.dumps({"error": str(exc), "tool": tc.name})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    raise AgentStepLimit(f"agent did not finish within {max_steps} steps")
