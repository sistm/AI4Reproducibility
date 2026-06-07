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
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

# A tool spec in OpenAI "tools" format. Kept as a plain dict so we never couple
# to a provider's typing. Built from the tool registry in a later step.
ToolSpec = dict[str, Any]

# Module logger. By default Python writes WARNING+ to stderr with no
# configuration, so retry events surface without the user setting LITELLM_LOG=
# DEBUG. INFO-level events (success-after-retry) are hidden by default but
# available to anyone who configures the logger.
_logger = logging.getLogger(__name__)


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

# HTTP status codes worth retrying: 408 (timeout), 429 (rate-limit) and 5xx are
# transient; other 4xx (auth, bad request, not found, context-window) will fail
# the same way on every attempt and only burn quota.
_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}

# Exception class names known to be non-transient across LiteLLM/OpenAI/Anthropic
# SDKs. Names (not isinstance) so the seam stays free of provider-typing coupling.
_NON_TRANSIENT_EXC_NAMES = frozenset({
    "AuthenticationError",
    "BadRequestError",
    "ContentPolicyViolationError",
    "ContextWindowExceededError",
    "InvalidRequestError",
    "NotFoundError",
    "PermissionDeniedError",
    "UnprocessableEntityError",
})


def _is_transient(exc: BaseException) -> bool:
    """Return True if ``exc`` is worth a retry; False if it would be wasted.

    Inspects an HTTP-style ``status_code`` first (most reliable signal across
    LiteLLM-mapped providers), then falls back to known exception class names.
    Unknown exceptions are treated as transient — the loop exists to absorb
    rare network blips, so the default-retry stance only sheds quota on
    classified-bad cases (avoiding the "retry an auth failure 5 times" pattern).
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in _TRANSIENT_STATUS:
            return True
        if 400 <= status < 500:
            return False  # auth, bad request, context-window — retry won't help
        return status >= 500  # other 5xx: still transient
    return type(exc).__name__ not in _NON_TRANSIENT_EXC_NAMES


class OutputTruncated(RuntimeError):
    """Raised when a final model answer was cut off at the token cap.

    Carries the partial ``text`` so callers can salvage what parsed before the
    cut, instead of silently treating a truncated answer as a parse error.
    """

    def __init__(self, text: str):
        super().__init__("model output truncated at the token limit")
        self.text = text


def _litellm_complete(
    model: str,
    messages: list[dict[str, Any]],
    tools: Sequence[ToolSpec],
    *,
    retries: int | None = None,
    backoff_cap: int | None = None,
) -> LLMResponse:
    """Default backend: call LiteLLM once and normalise the response.

    LiteLLM is imported here, not at module top, so importing this module — and
    unit-testing the loop with a fake backend — never requires LiteLLM.

    ``retries`` and ``backoff_cap`` override the values from :mod:`config`. Pass
    ``None`` (the default) to consult the global config — keeping the call-as-
    ``CompleteFn`` signature unchanged. Use :func:`with_retry_policy` to bind
    overrides for a specific call site without changing the ``CompleteFn`` type.
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

    eff_retries = retries if retries is not None else config.num_retries()
    eff_cap = backoff_cap if backoff_cap is not None else config.backoff_cap()

    # Retry in-process rather than delegating to LiteLLM's ``num_retries``: that
    # path imports ``tenacity``, a transitive dependency that — when absent —
    # crashes the call outright ("No module named 'tenacity'"), silently killing
    # a section. A small self-contained loop keeps retries working with no extra
    # dependency. Only transient errors are retried (rate-limit/timeout/5xx);
    # 4xx classes like auth or bad-request fail-fast — see _is_transient.
    #
    # Patch 0060d: every retry decision is logged so post-mortem analysis can
    # tell whether retries fired at all and how many burned before give-up. The
    # smoke run that motivated 0060c made this concrete: without per-attempt
    # logging it's impossible to distinguish "retry budget too small" from
    # "retry wiring broken" on a Synthesiser-Call-2 failure.
    for attempt in range(eff_retries + 1):
        try:
            response = litellm.completion(**kwargs)
            if attempt > 0:
                _logger.info(
                    "litellm.completion succeeded on retry %d/%d",
                    attempt, eff_retries,
                )
            break
        except Exception as exc:
            transient = _is_transient(exc)
            if attempt >= eff_retries or not transient:
                _logger.error(
                    "litellm.completion giving up at attempt %d/%d "
                    "(transient=%s, retries_remaining=%d): %s: %s",
                    attempt, eff_retries, transient,
                    max(0, eff_retries - attempt),
                    type(exc).__name__, exc,
                )
                raise
            sleep_s = min(2 ** attempt, eff_cap)
            _logger.warning(
                "litellm.completion attempt %d/%d failed (%s: %s); "
                "retrying after %ds (budget=%d, cap=%ds)",
                attempt, eff_retries, type(exc).__name__, exc,
                sleep_s, eff_retries, eff_cap,
            )
            time.sleep(sleep_s)
    message = response.choices[0].message

    calls: list[ToolCall] = []
    for tc in getattr(message, "tool_calls", None) or []:
        raw_args = tc.function.arguments
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
        calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

    finish_reason = getattr(response.choices[0], "finish_reason", None)
    # Patch 0067: surface output truncation as a WARNING. ``finish_reason ==
    # "length"`` is the smoking gun for hitting the max_tokens cap mid-emission
    # — the model wanted to keep going but was cut off. Downstream behaviour
    # depends on the caller: CQV deterministic-repair will salvage some
    # truncated output but lose any content past the cut, which is exactly the
    # smoke-C pattern (raw ended mid-object, json_repair kept ``status`` +
    # ``repository_audit`` and dropped everything after). Without this log the
    # cap is invisible — the artifact looks like generic "model emitted bad
    # JSON" rather than "we asked for too much in one shot".
    if finish_reason == "length":
        _logger.warning(
            "litellm.completion hit max_tokens cap (finish_reason=length); "
            "output truncated at %d chars. Bump AI4R_MAX_TOKENS or shrink the "
            "prompt. Currently max_tokens=%d",
            len(message.content or ""), config.max_tokens(),
        )
    elif finish_reason not in (None, "stop", "tool_calls"):
        # Anything else (e.g. "content_filter", a provider-specific code, ...)
        # is unusual enough to surface — INFO not WARNING so it doesn't drown
        # the logs but is visible to anyone looking.
        _logger.info(
            "litellm.completion unusual finish_reason=%r", finish_reason,
        )
    return LLMResponse(text=message.content, tool_calls=calls, finish_reason=finish_reason)


def with_retry_policy(
    *, retries: int, backoff_cap: int | None = None
) -> CompleteFn:
    """Return a :data:`CompleteFn` wrapping the default backend with a fixed
    retry policy.

    Use at call sites whose retry budget should differ from the global default
    (e.g. critical write-path calls that should ride out longer gateway blips).
    The returned function has the standard ``CompleteFn`` signature, so it
    drops into any place a ``complete_fn`` is expected without touching the
    type alias or breaking injected test fakes.

    ``backoff_cap=None`` falls back to the global config cap.
    """
    def _wrapped(
        model: str,
        messages: list[dict[str, Any]],
        tools: Sequence[ToolSpec],
    ) -> LLMResponse:
        return _litellm_complete(
            model, messages, tools,
            retries=retries, backoff_cap=backoff_cap,
        )
    return _wrapped


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
