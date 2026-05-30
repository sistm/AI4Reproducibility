"""KBE stage runner: paper PDF -> structured ``kbe_output.json`` + ``notes.md``.

This is the first pipeline stage wired to a real model. It loads the KBE
SKILL as the system prompt, exposes only the PDF tools to the model, runs the
agent loop (:func:`tools.orchestrator.llm.run_agent`), then writes the two
output files the contract requires (see ``agents/knowledge-base-extraction/
SKILL.md`` and LOGIC.md §3.1).

Two contract guarantees are enforced here rather than trusted to the model:

* The stage NEVER raises. Any failure — missing PDF, model error, unparseable
  output — is caught and written as a ``status != "success"`` output, so the
  post-flight validator always finds well-formed files (degraded continuation,
  LOGIC.md §6).
* ``paper_id`` is always the kebab-case ``review_title``, and
  ``extraction_timestamp`` / required arrays / ``status`` are always present,
  whatever the model returned. That keeps ``kbe_output.json`` valid against
  ``validate_review.sh`` (which requires top-level ``paper_id`` and ``status``).
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

# Tools KBE is allowed to call (LOGIC.md §3.1). Deliberately narrow.
KBE_TOOLS = ["pdf2text", "clean_pdf_text"]

# Array fields that must always be present in kbe_output.json.
_ARRAY_FIELDS = (
    "identified_assumptions",
    "statistical_methods",
    "data_generation_processes",
    "reproducibility_gaps",
)

_KEBAB = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _skill_prompt() -> str:
    """Load the KBE SKILL as the system prompt (install-safe via resources)."""
    resource = importlib.resources.files("agents").joinpath(
        "knowledge-base-extraction/SKILL.md"
    )
    return resource.read_text(encoding="utf-8")


def _user_prompt(pdf_path: Path, review_title: str) -> str:
    """Instruction prompt for one extraction run."""
    fields = ", ".join(
        ["paper_title", "structured_knowledge", *_ARRAY_FIELDS, "partial_data", "notes"]
    )
    return (
        f"The manuscript PDF for review '{review_title}' is at:\n  {pdf_path}\n\n"
        "Read it using the pdf2text tool, then clean_pdf_text, and perform the "
        "knowledge-base extraction described in your instructions.\n\n"
        "Return ONLY a single JSON object as your final message — no prose, no "
        "markdown fences. Include these fields: "
        f"{fields}. Use null for paper_title if you cannot read the title, and "
        "empty arrays where you found nothing. Do not include paper_id, status, "
        "or extraction_timestamp; those are set by the orchestrator."
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _failure_output(
    review_title: str, failure_mode: str, failure_reason: str, status: str = "failed"
) -> dict[str, Any]:
    """Build a contract-valid output for a non-success run."""
    return {
        "paper_id": review_title,
        "paper_title": None,
        "extraction_timestamp": _now(),
        "status": status,
        "failure_mode": failure_mode,
        "failure_reason": failure_reason,
        "structured_knowledge": None,
        "identified_assumptions": [],
        "statistical_methods": [],
        "data_generation_processes": [],
        "reproducibility_gaps": [],
        "partial_data": None,
        "notes": "See notes.md for context.",
    }


def _parse_model_json(text: str) -> dict[str, Any]:
    """Parse the model's final message as JSON, tolerating ``` fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # drop a leading ```json / ``` fence and the trailing ```
        stripped = re.sub(r"^```[a-zA-Z0-9]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped.strip())
    obj = json.loads(stripped)
    if not isinstance(obj, dict):
        raise ValueError("model returned JSON but not an object")
    return obj


def _normalise(obj: dict[str, Any], review_title: str) -> dict[str, Any]:
    """Force the orchestrator-owned fields and fill any missing required keys."""
    obj["paper_id"] = review_title  # authoritative, always the slug
    obj.setdefault("status", "success")
    obj["extraction_timestamp"] = obj.get("extraction_timestamp") or _now()
    obj.setdefault("paper_title", None)
    obj.setdefault("structured_knowledge", None)
    obj.setdefault("partial_data", None)
    obj.setdefault("notes", "")
    for field in _ARRAY_FIELDS:
        value = obj.get(field)
        obj[field] = value if isinstance(value, list) else []
    return obj


def _write_outputs(review_dir: Path, output: dict[str, Any]) -> None:
    """Write kbe_output.json and notes.md, and log the status."""
    kbe_dir = review_dir / "kbe"
    kbe_dir.mkdir(parents=True, exist_ok=True)
    (kbe_dir / "kbe_output.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    notes = output.get("notes") or ""
    if output["status"] != "success":
        notes = (
            f"# KBE failure\n\n"
            f"- mode: {output.get('failure_mode')}\n"
            f"- reason: {output.get('failure_reason')}\n\n{notes}"
        )
    (kbe_dir / "notes.md").write_text(str(notes), encoding="utf-8")

    logs_dir = review_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / "workflow.log").open("a", encoding="utf-8") as log:
        log.write(f"{_now()} KBE status={output['status']} "
                  f"mode={output.get('failure_mode', '-')}\n")


def run_kbe(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
    max_steps: int = 12,
) -> dict[str, Any]:
    """Run the KBE stage for ``review_title`` and return the written output dict.

    ``root`` is the directory containing ``ai4r/``. ``model`` defaults to the
    KBE stage model from config; ``complete_fn`` defaults to the LiteLLM
    backend and can be injected with a fake for testing.
    """
    review_dir = Path(root) / "ai4r" / review_title
    pdf_path = review_dir / "input" / "paper.pdf"

    if not _KEBAB.match(review_title):
        output = _failure_output(
            review_title, "bad_review_title",
            f"review_title is not kebab-case: {review_title!r}",
        )
        _write_outputs(review_dir, output)
        return output

    if not pdf_path.is_file():
        output = _failure_output(
            review_title, "pdf_not_found", f"input/paper.pdf is absent at {pdf_path}"
        )
        _write_outputs(review_dir, output)
        return output

    agent_kwargs: dict[str, Any] = {
        "system": _skill_prompt(),
        "user": _user_prompt(pdf_path, review_title),
        "model": model or model_for("kbe"),
        "tools": registry_specs(KBE_TOOLS),
        "max_steps": max_steps,
    }
    if complete_fn is not None:
        agent_kwargs["complete_fn"] = complete_fn

    try:
        text = run_agent(**agent_kwargs)
    except Exception as exc:  # never let the stage crash the pipeline
        output = _failure_output(
            review_title, "parse_error", f"agent run failed: {exc}", status="partial"
        )
        _write_outputs(review_dir, output)
        return output

    try:
        parsed = _parse_model_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        output = _failure_output(
            review_title, "parse_error",
            f"model output was not valid JSON: {exc}", status="partial",
        )
        output["notes"] = f"Raw model output (truncated):\n{text[:2000]}"
        _write_outputs(review_dir, output)
        return output

    output = _normalise(parsed, review_title)
    _write_outputs(review_dir, output)
    return output


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.kbe <review_title> [--root DIR]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the KBE stage.")
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    parser.add_argument("--model", default=None, help="LiteLLM model override")
    args = parser.parse_args(argv)

    output = run_kbe(args.review_title, root=args.root, model=args.model)
    print(f"KBE {output['status']} -> {args.root}/ai4r/{args.review_title}/kbe/")
    return 0 if output["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
