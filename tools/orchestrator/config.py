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
    "er": "mistral/mistral-large-latest",
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
_DEFAULT_BACKOFF_CAP = 8  # seconds, cap on exponential backoff between retries

# Per-call-site retry policy overrides. Keys are opaque tags chosen by the call
# site, not stage names — they identify a specific call whose retry posture
# matters (e.g. Synthesiser revisions Call 2 is the critical write-path call
# whose transient failure forces the whole Review to degrade). A higher budget
# and longer backoff cap give it real headroom over typical gateway blips,
# without affecting cheap one-shot calls that should fail fast.
_STAGE_RETRY_DEFAULTS: dict[str, int] = {
    "synthesis_revisions": 5,
}
_STAGE_BACKOFF_DEFAULTS: dict[str, int] = {
    "synthesis_revisions": 30,
}


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


def num_retries(key: str | None = None) -> int:
    """Automatic retries on a failed/transient completion request.

    Precedence: per-key env (``AI4R_NUM_RETRIES_<KEY>``) > per-key default >
    global env (``AI4R_NUM_RETRIES``) > global default. A per-key default
    intentionally bypasses the global env override — when a call site has been
    tagged as critical, a routine global tweak should not silently downgrade it.
    To disable the per-key bump, set the per-key env var explicitly.
    """
    if key:
        per_key = os.environ.get(f"AI4R_NUM_RETRIES_{key.upper()}")
        if per_key:
            try:
                return int(per_key)
            except ValueError:
                pass
        if key in _STAGE_RETRY_DEFAULTS:
            return _STAGE_RETRY_DEFAULTS[key]
    return _int_env("AI4R_NUM_RETRIES", _DEFAULT_NUM_RETRIES)


def backoff_cap(key: str | None = None) -> int:
    """Cap (seconds) on exponential backoff between retries.

    Same precedence as :func:`num_retries`. Default cap is short so retries
    finish quickly on common transients; per-key bump is for calls where
    riding out a longer gateway hiccup is worth the wait.
    """
    if key:
        per_key = os.environ.get(f"AI4R_BACKOFF_CAP_{key.upper()}")
        if per_key:
            try:
                return int(per_key)
            except ValueError:
                pass
        if key in _STAGE_BACKOFF_DEFAULTS:
            return _STAGE_BACKOFF_DEFAULTS[key]
    return _int_env("AI4R_BACKOFF_CAP", _DEFAULT_BACKOFF_CAP)
