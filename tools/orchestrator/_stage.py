"""Helpers shared by the KBE, CQV, ER and Review stage runners.

Extracted once the stages made the duplication concrete (rule of three): each
needs the same kebab-case check, UTC timestamp, fence-tolerant JSON-object
parser, SKILL loader, ``workflow.log`` append, and the two-step JSON repair
salvage (deterministic ``json_repair`` then a single model reprompt). Only the
genuinely identical scaffolding lives here — stage-specific output assembly
stays in each stage module, so this stays a small box of utilities rather than
a framework.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.orchestrator.llm import CompleteFn, run_agent

# A review_title slug: lowercase alphanumerics and hyphens, not hyphen-initial.
KEBAB = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def is_kebab(review_title: str) -> bool:
    """Return True if ``review_title`` is a valid kebab-case slug."""
    return bool(KEBAB.match(review_title))


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string (the stages' timestamp format)."""
    return datetime.now(UTC).isoformat()


def load_skill(relpath: str) -> str:
    """Read a stage SKILL.md from the ``agents`` package by relative path.

    e.g. ``load_skill("review/SKILL.md")``. Uses importlib.resources so it works
    whether the package is installed or run from a source checkout.
    """
    resource = importlib.resources.files("agents").joinpath(relpath)
    return resource.read_text(encoding="utf-8")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a model response as a JSON object, tolerating ```json fences.

    Raises ``ValueError`` / ``json.JSONDecodeError`` if the text is not a JSON
    object — callers turn that into a ``status != success`` output.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped.strip())
    obj = json.loads(stripped)
    if not isinstance(obj, dict):
        raise ValueError("model returned JSON but not an object")
    return obj


def append_log(review_dir: Path, message: str) -> None:
    """Append a timestamped line to ``<review_dir>/logs/workflow.log``.

    Creates the logs directory if needed. ``message`` is the text after the
    timestamp, e.g. ``"KBE status=success mode=-"``.
    """
    logs_dir = review_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / "workflow.log").open("a", encoding="utf-8") as log:
        log.write(f"{now_iso()} {message}\n")


_REPAIR_SYSTEM = (
    "You repair malformed JSON. The user gives a string that was meant to be a "
    "single JSON object but failed to parse. Return ONLY the corrected, valid "
    "JSON object with exactly the same content — no prose, no markdown fences. "
    "Fix delimiters and escaping; do not add, drop, or summarise any content."
)


def _repair_json_deterministic(text: str) -> dict[str, Any] | None:
    """Best-effort structural repair of malformed model JSON — no model call.

    Uses ``json_repair`` (optional, lazy-imported) to fix the structural slips
    LLMs make in large nested output: missing commas, trailing commas, and
    array/object confusion (e.g. ``"evidence": {obj}, {obj}]``). Returns the
    parsed object, or None if the library is absent or yields a non-object.
    Deterministic and never raises, so it is tried before the model reprompt.
    """
    try:
        from json_repair import repair_json
    except ImportError:
        return None
    try:
        obj = repair_json(text, return_objects=True)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _repair_json_once(
    bad_text: str, error: Exception, *, model: str, complete_fn: CompleteFn | None
) -> dict[str, Any] | None:
    """One best-effort reprompt to turn malformed model JSON into valid JSON.

    LLMs reliably fix their own JSON when told the exact parser error (the
    observed failure was a missing comma where a code snippet was embedded).
    Returns the parsed object, or None if the repair also fails to parse.
    Never raises.
    """
    user = (
        f"This was supposed to be one JSON object but failed to parse with:\n"
        f"{error}\n\nReturn the corrected JSON object, same content:\n\n{bad_text}"
    )
    agent_kwargs: dict[str, Any] = {"system": _REPAIR_SYSTEM, "user": user, "model": model}
    if complete_fn is not None:
        agent_kwargs["complete_fn"] = complete_fn
    try:
        return parse_json_object(run_agent(**agent_kwargs))
    except Exception:
        return None
