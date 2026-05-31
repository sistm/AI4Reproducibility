"""KBE stage runner: paper PDF -> structured ``kbe_output.json`` + ``notes.md``.

Sectioned extraction. A full single-shot JSON extraction of a real manuscript
overruns the model's output-token cap and gets truncated, so KBE instead:

1. extracts the PDF text *once*, deterministically (no model tool loop — the
   "tools" were a fixed two-step sequence, so the orchestrator runs them
   directly; this also removes any dependence on the gateway forwarding tool
   calls); then
2. makes one bounded model call per knowledge category, each returning a small
   JSON object, and assembles them.

Each call's *output* stays well under the cap regardless of paper length; the
paper text rides in the input, comfortably inside the context window.

Contract guarantees enforced here (see ``agents/knowledge-base-extraction/
SKILL.md`` and LOGIC.md §6): the stage never raises; the orchestrator owns
``paper_id`` (always the kebab-case title) and ``extraction_timestamp``; and a
partial extraction reports which categories succeeded vs failed in
``partial_data`` rather than discarding everything.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.orchestrator._stage import (
    append_log,
    is_kebab,
    load_skill,
    now_iso,
    parse_json_object,
)
from tools.orchestrator.config import model_for
from tools.orchestrator.llm import CompleteFn, run_agent

# Minimum cleaned-text length below which we treat extraction as having failed.
_MIN_TEXT_CHARS = 500

# Ordered: one model call per entry. paper_title yields a string; the rest yield
# JSON arrays. Keys match the kbe_output.json field names.
_TITLE_FIELD = "paper_title"
_ARRAY_FIELDS = (
    "structured_knowledge",
    "identified_assumptions",
    "statistical_methods",
    "data_generation_processes",
    "reproducibility_gaps",
)

_SECTION_GUIDANCE: dict[str, str] = {
    "paper_title": "the manuscript's full title",
    "structured_knowledge": "atomic knowledge blocks (methods, metrics, results, "
    "datasets), each an object describing one item",
    "identified_assumptions": "explicit and implicit modelling/statistical "
    "assumptions, each with a short category and risk",
    "statistical_methods": "statistical and algorithmic methods used or proposed",
    "data_generation_processes": "data sources, sampling, measurement and "
    "preprocessing steps",
    "reproducibility_gaps": "concrete reproducibility gaps (missing seeds, "
    "unspecified versions, undefined preprocessing, unavailable data)",
}


def _default_extract(pdf_path: Path) -> str:
    """Extract and clean PDF text via the registry tools (lazy import).

    The *registered* ``pdf2text`` and ``clean_pdf_text`` tools return the text
    as a plain string and raise ``RuntimeError`` on failure (they wrap the
    raw kbe_agent functions, which return dicts). So we chain them directly and
    let any failure propagate to run_kbe's handler (-> ``pdf_unreadable``).
    """
    from tools.tools import run_tool

    raw_text = run_tool("pdf2text", pdf_path=str(pdf_path))
    return run_tool("clean_pdf_text", raw_text=raw_text)


def _section_prompt(field: str, guidance: str, paper_text: str) -> str:
    if field == _TITLE_FIELD:
        shape = f'{{"{field}": "<string, or null if not found>"}}'
        kind = "a JSON string"
    else:
        shape = f'{{"{field}": [ ... ]}}'
        kind = "a JSON array (use [] if you find nothing)"
    return (
        "Manuscript text:\n\n"
        f"{paper_text}\n\n"
        f"From the manuscript above, extract {guidance}.\n"
        f"Return ONLY a single JSON object of the form {shape} — no prose, no "
        f"markdown fences. The value must be {kind}."
    )


def _run_section(
    paper_text: str, field: str, guidance: str, model: str, complete_fn: CompleteFn | None
) -> str:
    kwargs: dict[str, Any] = {
        "system": load_skill("knowledge-base-extraction/SKILL.md"),
        "user": _section_prompt(field, guidance, paper_text),
        "model": model,
        "tools": (),
        "max_steps": 1,
    }
    if complete_fn is not None:
        kwargs["complete_fn"] = complete_fn
    return run_agent(**kwargs)


def _failure_output(
    review_title: str, failure_mode: str, failure_reason: str, status: str = "failed"
) -> dict[str, Any]:
    return {
        "paper_id": review_title,
        "paper_title": None,
        "extraction_timestamp": now_iso(),
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


def _assemble(
    review_title: str,
    extracted: dict[str, Any],
    failed: dict[str, str],
    transport_seen: bool,
) -> dict[str, Any]:
    title = extracted.get(_TITLE_FIELD)
    output: dict[str, Any] = {
        "paper_id": review_title,
        "paper_title": title if isinstance(title, str) and title else None,
        "extraction_timestamp": now_iso(),
        "status": "success",
        "partial_data": None,
        "notes": "",
    }
    for field in _ARRAY_FIELDS:
        value = extracted.get(field)
        output[field] = value if isinstance(value, list) else []

    if not extracted:
        output["status"] = "failed"
        output["failure_mode"] = "llm_request_failed" if transport_seen else "parse_error"
        output["failure_reason"] = "; ".join(f"{k}: {v}" for k, v in failed.items())[:1000]
        output["structured_knowledge"] = None
    elif failed:
        output["status"] = "partial"
        output["failure_mode"] = "template_partial"
        output["failure_reason"] = "; ".join(f"{k}: {v}" for k, v in failed.items())[:1000]
        output["partial_data"] = {
            "sections_extracted": sorted(extracted),
            "sections_failed": sorted(failed),
        }
        output["notes"] = f"Categories not extracted: {', '.join(sorted(failed))}."
    return output


def _write_outputs(review_dir: Path, output: dict[str, Any]) -> None:
    kbe_dir = review_dir / "kbe"
    kbe_dir.mkdir(parents=True, exist_ok=True)
    (kbe_dir / "kbe_output.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    notes = output.get("notes") or ""
    if output["status"] != "success":
        notes = (
            f"# KBE {output['status']}\n\n"
            f"- mode: {output.get('failure_mode')}\n"
            f"- reason: {output.get('failure_reason')}\n\n{notes}"
        )
    elif not notes.strip():
        # The success path carries no free-form notes, but notes.md is a
        # contract output and validate_review.sh rejects a <2-byte file, so
        # write a minimal non-empty summary pointing at the structured output.
        notes = (
            f"# KBE notes — {output['paper_id']}\n\n"
            "status: success. No free-form notes; the structured fields are in "
            "kbe_output.json.\n"
        )
    (kbe_dir / "notes.md").write_text(str(notes), encoding="utf-8")

    append_log(
        review_dir,
        f"KBE status={output['status']} mode={output.get('failure_mode', '-')}",
    )
def run_kbe(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
    extract_fn: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    """Run the KBE stage for ``review_title`` and return the written output dict.

    ``extract_fn`` turns the PDF path into cleaned text; it defaults to the
    registry PDF tools and can be injected with a fake for testing.
    """
    review_dir = Path(root) / "ai4r" / review_title
    pdf_path = review_dir / "input" / "paper.pdf"

    if not is_kebab(review_title):
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

    extract = extract_fn or _default_extract
    try:
        paper_text = extract(pdf_path)
    except Exception as exc:
        output = _failure_output(
            review_title, "pdf_unreadable", f"could not extract text: {exc}"
        )
        _write_outputs(review_dir, output)
        return output

    if len(paper_text.strip()) < _MIN_TEXT_CHARS:
        output = _failure_output(
            review_title, "text_too_short",
            f"extracted text is only {len(paper_text.strip())} chars",
        )
        _write_outputs(review_dir, output)
        return output

    model_name = model or model_for("kbe")
    extracted: dict[str, Any] = {}
    failed: dict[str, str] = {}
    transport_seen = False

    for field, guidance in _SECTION_GUIDANCE.items():
        try:
            raw = _run_section(paper_text, field, guidance, model_name, complete_fn)
        except Exception as exc:  # transport / LLM call failure for this section
            failed[field] = f"llm request failed: {exc}"
            transport_seen = True
            continue
        try:
            parsed = parse_json_object(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            failed[field] = f"invalid JSON: {exc}"
            continue
        extracted[field] = parsed.get(field)

    output = _assemble(review_title, extracted, failed, transport_seen)
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
