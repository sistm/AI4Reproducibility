"""CQV stage runner: extracted code -> ``cqv_output.json`` + ``repo_analysis.md``.

Second pipeline stage wired to a model, parallel to :mod:`tools.orchestrator.kbe`.
It loads the CQV SKILL as the system prompt, exposes only the code-inspection
and static-check tools (LOGIC.md §4 limits CQV to the extracted code — never the
paper or KBE output, for bias control), runs the agent loop, and writes the two
output files the contract requires (``agents/code-quality-verification/SKILL.md``).

Contract specifics that differ from KBE and are enforced here:

* timestamp field is ``audit_timestamp`` (not ``extraction_timestamp``);
* CQV MUST NOT emit ``paper_title`` (context-boundary rule) — it is stripped;
* a non-``success`` status MUST carry at least one ``reproducibility_blockers``
  entry, so Review can mark items Unverified rather than silently passing them.

As with KBE, the stage never raises (missing/empty code, model error, or
unparseable output become ``status != "success"`` outputs) and the orchestrator
owns ``paper_id`` so ``validate_review.sh`` (requiring ``paper_id`` + ``status``)
always passes.

Note: this duplicates a few small helpers from :mod:`tools.orchestrator.kbe`
(slug check, JSON-fence parsing, timestamp). That is deliberate for now —
extracting a shared ``_stage`` helper is worth doing once Review makes it three
users of the pattern (rule of three), rather than refactoring committed code here.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.orchestrator.config import model_for
from tools.orchestrator.llm import CompleteFn, run_agent
from tools.orchestrator.tool_specs import registry_specs

# Tools CQV is allowed to call. Code inspection + static checks only; no
# create_file (the orchestrator writes outputs), no PDF tools (LOGIC.md §4).
CQV_TOOLS = [
    "list_files",
    "read_file",
    "get_dependencies",
    "extract_zip",
    "run_static_check",
    "list_static_checks",
]

_ALLOWED_STATUS = {"success", "partial", "failed"}
_KEBAB = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _skill_prompt() -> str:
    resource = importlib.resources.files("agents").joinpath(
        "code-quality-verification/SKILL.md"
    )
    return resource.read_text(encoding="utf-8")


def _user_prompt(assets_dir: Path, review_title: str) -> str:
    return (
        f"The extracted code supplement for review '{review_title}' is under:\n"
        f"  {assets_dir}\n\n"
        "Inspect it with list_files, read_file, get_dependencies and extract_zip, "
        "and run the static checks with run_static_check (use list_static_checks "
        "to see what is available). Perform the code-quality audit described in "
        "your instructions, including the items in your also_enforces checklist "
        "scope.\n\n"
        "Return ONLY a single JSON object as your final message — no prose, no "
        "markdown fences — with these fields: status (success|partial|failed), "
        "repository_audit, code_method_alignment, dependency_validation, "
        "execution_readiness, reproducibility_blockers, partial_data, notes. "
        "Do NOT include paper_id, audit_timestamp, or paper_title; the first two "
        "are set by the orchestrator and the third is outside your context."
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_blocker(reason: str | None) -> dict[str, Any]:
    return {
        "id": "BLOCKER-0",
        "severity": "CRITICAL",
        "description": "Verification incomplete; see repo_analysis.md.",
        "evidence": reason or "ai4r/<review_title>/logs/workflow.log",
    }


def _failure_output(
    review_title: str, failure_mode: str, failure_reason: str, status: str = "failed"
) -> dict[str, Any]:
    return {
        "paper_id": review_title,
        "audit_timestamp": _now(),
        "status": status,
        "failure_mode": failure_mode,
        "failure_reason": failure_reason,
        "repository_audit": None,
        "code_method_alignment": None,
        "dependency_validation": None,
        "execution_readiness": "unknown",
        "reproducibility_blockers": [_default_blocker(failure_reason)],
        "partial_data": None,
        "notes": "See repo_analysis.md for context.",
    }


def _parse_model_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped.strip())
    obj = json.loads(stripped)
    if not isinstance(obj, dict):
        raise ValueError("model returned JSON but not an object")
    return obj


def _normalise(obj: dict[str, Any], review_title: str) -> dict[str, Any]:
    obj["paper_id"] = review_title  # authoritative
    obj.pop("paper_title", None)  # rule 3: CQV must not emit paper_title

    status = obj.get("status")
    obj["status"] = status if status in _ALLOWED_STATUS else "success"
    obj["audit_timestamp"] = obj.get("audit_timestamp") or _now()
    obj.setdefault("repository_audit", None)
    obj.setdefault("code_method_alignment", None)
    obj.setdefault("dependency_validation", None)
    obj["execution_readiness"] = obj.get("execution_readiness") or "unknown"
    obj.setdefault("partial_data", None)
    obj.setdefault("notes", "")

    blockers = obj.get("reproducibility_blockers")
    obj["reproducibility_blockers"] = blockers if isinstance(blockers, list) else []
    # rule 5: a non-success status must always carry at least one blocker.
    if obj["status"] != "success" and not obj["reproducibility_blockers"]:
        obj["reproducibility_blockers"] = [_default_blocker(obj.get("failure_reason"))]
    return obj


def _write_outputs(review_dir: Path, output: dict[str, Any]) -> None:
    cqv_dir = review_dir / "cqv"
    cqv_dir.mkdir(parents=True, exist_ok=True)
    (cqv_dir / "cqv_output.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    analysis = output.get("notes") or ""
    if output["status"] != "success":
        analysis = (
            f"# CQV failure\n\n"
            f"- mode: {output.get('failure_mode')}\n"
            f"- reason: {output.get('failure_reason')}\n\n{analysis}"
        )
    (cqv_dir / "repo_analysis.md").write_text(str(analysis), encoding="utf-8")

    logs_dir = review_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / "workflow.log").open("a", encoding="utf-8") as log:
        log.write(f"{_now()} CQV status={output['status']} "
                  f"mode={output.get('failure_mode', '-')}\n")


def run_cqv(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
    max_steps: int = 20,
) -> dict[str, Any]:
    """Run the CQV stage for ``review_title`` and return the written output dict.

    ``root`` is the directory containing ``ai4r/``. ``model`` defaults to the
    CQV stage model from config; ``complete_fn`` defaults to the LiteLLM backend
    and can be injected with a fake for testing.
    """
    review_dir = Path(root) / "ai4r" / review_title
    assets_dir = review_dir / "input" / "assets"

    if not _KEBAB.match(review_title):
        output = _failure_output(
            review_title, "bad_review_title",
            f"review_title is not kebab-case: {review_title!r}",
        )
        _write_outputs(review_dir, output)
        return output

    if not assets_dir.is_dir() or not any(p.is_file() for p in assets_dir.rglob("*")):
        output = _failure_output(
            review_title, "assets_directory_empty",
            f"no files found under {assets_dir}",
        )
        _write_outputs(review_dir, output)
        return output

    agent_kwargs: dict[str, Any] = {
        "system": _skill_prompt(),
        "user": _user_prompt(assets_dir, review_title),
        "model": model or model_for("cqv"),
        "tools": registry_specs(CQV_TOOLS),
        "max_steps": max_steps,
    }
    if complete_fn is not None:
        agent_kwargs["complete_fn"] = complete_fn

    try:
        text = run_agent(**agent_kwargs)
    except Exception as exc:  # transport / LLM call failure: no audit happened
        output = _failure_output(
            review_title, "llm_request_failed", f"LLM request failed: {exc}",
            status="failed",
        )
        _write_outputs(review_dir, output)
        return output

    try:
        parsed = _parse_model_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        output = _failure_output(
            review_title, "output_parse_failed",
            f"model output was not valid JSON: {exc}", status="partial",
        )
        output["notes"] = f"Raw model output (truncated):\n{text[:2000]}"
        # keep the default blocker from _failure_output
        _write_outputs(review_dir, output)
        return output

    output = _normalise(parsed, review_title)
    _write_outputs(review_dir, output)
    return output


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.cqv <review_title> [--root DIR]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the CQV stage.")
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    parser.add_argument("--model", default=None, help="LiteLLM model override")
    args = parser.parse_args(argv)

    output = run_cqv(args.review_title, root=args.root, model=args.model)
    print(f"CQV {output['status']} -> {args.root}/ai4r/{args.review_title}/cqv/")
    return 0 if output["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
