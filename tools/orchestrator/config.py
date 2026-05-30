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
