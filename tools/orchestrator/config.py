"""Per-stage model routing (LOGIC.md §5f).

Each pipeline stage may run on a different model. Values are LiteLLM model
strings in ``"<provider>/<model>"`` form, e.g. ``"mistral/mistral-large-latest"``
or ``"anthropic/claude-..."``. Swapping providers is a string change here; the
orchestrator code never names a provider.

Any stage default can be overridden at runtime with an environment variable
``AI4R_MODEL_<STAGE>`` (uppercased), e.g.::

    AI4R_MODEL_KBE=mistral/mistral-small-latest
    AI4R_MODEL_REVIEW=anthropic/claude-opus-4-...

These defaults are configuration, not contracts — adjust them freely.
"""

from __future__ import annotations

import os

STAGE_MODELS: dict[str, str] = {
    "kbe": "mistral/mistral-large-latest",
    "cqv": "mistral/mistral-large-latest",
    "review": "mistral/mistral-large-latest",
    "critique": "mistral/mistral-large-latest",
}

_ENV_PREFIX = "AI4R_MODEL_"


def model_for(stage: str) -> str:
    """Return the model string for ``stage``, honouring an env override.

    Raises ``KeyError`` for a stage with neither an override nor a default.
    """
    override = os.environ.get(_ENV_PREFIX + stage.upper())
    if override:
        return override
    try:
        return STAGE_MODELS[stage]
    except KeyError:
        raise KeyError(
            f"no model configured for stage {stage!r}; "
            f"known stages: {sorted(STAGE_MODELS)}"
        ) from None


# ---------------------------------------------------------------------------
# LLM call parameters
# ---------------------------------------------------------------------------
# Applied by the LiteLLM backend in llm.py. Read at call time so env overrides
# take effect without reimport. Note: max_tokens caps how much the model may
# *generate* per call — it is separate from, and far smaller than, the model's
# context window. Override via AI4R_MAX_TOKENS / AI4R_REQUEST_TIMEOUT /
# AI4R_NUM_RETRIES.

_DEFAULT_MAX_TOKENS = 12000
_DEFAULT_REQUEST_TIMEOUT = 120  # seconds
_DEFAULT_NUM_RETRIES = 2


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def max_tokens() -> int:
    """Output-token cap per completion (not the context window)."""
    return _int_env("AI4R_MAX_TOKENS", _DEFAULT_MAX_TOKENS)


def request_timeout() -> int:
    """Per-request timeout in seconds, so a stalled gateway fails fast."""
    return _int_env("AI4R_REQUEST_TIMEOUT", _DEFAULT_REQUEST_TIMEOUT)


def num_retries() -> int:
    """Automatic retries on a failed/transient completion request."""
    return _int_env("AI4R_NUM_RETRIES", _DEFAULT_NUM_RETRIES)
