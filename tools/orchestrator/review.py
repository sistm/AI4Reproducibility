"""Review stage runner: upstream KBE/CQV outputs -> the four Review files.

Review is synthesis, not execution (LOGIC.md §3.4): it reads the upstream JSON
outputs, judges reproducibility, and writes ``review/{risk_matrix.json,
final_review.md, checklist.md, exhaustive_audit_report.md}``. It never reads the
PDF, runs code, or re-runs static checks.

Contract guarantees enforced here:

* The stage never raises; any failure still writes all four files (a missing
  output file is a hard pipeline failure, SKILL behavioural rule).
* The orchestrator owns ``paper_id`` (the kebab-case title), ``assessed_at``,
  ``assessment_status`` and ``upstream_status``; ``paper_title`` is copied from
  ``kbe_output.json`` (rule 5), never invented.
* ``risk_matrix.json`` always carries the ten keys validate_review.sh checks:
  paper_id, paper_title, assessed_at, assessment_status, risk_score, risk_level,
  verdict, issues, required_changes, upstream_status.

Output is sectioned (one model call for the risk-matrix core, one per markdown
report) so no single response overruns the output-token cap.

NOTE: KBE, CQV and Review share this stage pattern (load SKILL -> sectioned
toolless calls -> parse -> assemble -> never raise -> orchestrator owns identity
-> write). The identical scaffolding (slug check, timestamp, JSON-fence parsing,
SKILL load, workflow-log append) now lives in :mod:`tools.orchestrator._stage`.
"""

from __future__ import annotations

import json
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

_VERDICTS = {"ACCEPT", "MINOR REVISION", "MAJOR REVISION", "REJECT"}
_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_FAILED_STATUSES = {"failed", "missing", "unreadable", "unknown"}

# The three markdown outputs and what each should contain.
_MD_OUTPUTS: dict[str, str] = {
    "final_review.md": "an executive Final Review: overall assessment, the verdict "
    "and its justification, and the key recommended changes",
    "checklist.md": (
        "the Biometrical Journal reproducibility checklist for this submission, "
        "following the format in agents/review/assets/review-template.md EXACTLY. "
        "Rules: (1) Emit all 24 checklist.yaml items in the order and sections "
        "shown in the template — Documentation, Completeness, Organisation, "
        "Reproducibility, Code Quality, Packaging, Result Verification. "
        "(2) For each item use one of three verdict tokens: PASS (requirement met "
        "with evidence), FAIL (requirement not met — cite file:line), or UNVERIFIED "
        "(could not assess — name the upstream cause). "
        "(3) Render a checked checkbox [x] for PASS, unchecked [ ] for FAIL and "
        "UNVERIFIED. "
        "(4) Follow each item's description with a single evidenced audit note "
        "sentence. "
        "(5) Append a bold 'Required action:' sub-bullet ONLY on FAIL items. "
        "(6) Close with the summary table and numbered required-actions list from "
        "the template. "
        "(7) Never invent items not in checklist.yaml; never omit items."
    ),
    "exhaustive_audit_report.md": "a detailed audit report: an Inputs section "
    "quoting each upstream status and failure_mode, then the CQV and KBE findings "
    "organised by severity, each cited by evidence path",
}


def _load_upstream(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Return (parsed dict or None, status string) for an upstream output."""
    if not path.is_file():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None, "unreadable"
    if not isinstance(data, dict):
        return None, "unreadable"
    return data, str(data.get("status", "unknown"))


def _status_entry(data: dict[str, Any] | None, status: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"status": status}
    if isinstance(data, dict) and data.get("failure_mode"):
        entry["failure_mode"] = data["failure_mode"]
    return entry


def _level_from_score(score: int) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MEDIUM"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def _score_from_level(level: str) -> int:
    return {"LOW": 12, "MEDIUM": 38, "HIGH": 63, "CRITICAL": 88}.get(level, 50)


def _context_blob(kbe: Any, cqv: Any, er: Any) -> str:
    def one(name: str, data: Any) -> str:
        if data is None:
            return f"{name}_output: (unavailable)"
        return f"{name}_output:\n{json.dumps(data, ensure_ascii=False)[:6000]}"

    parts = [one("kbe", kbe), one("cqv", cqv)]
    if er is not None:
        parts.append(one("er", er))
    return "\n\n".join(parts)


def _risk_prompt(context: str, assessment_status: str) -> str:
    return (
        f"Upstream outputs (assessment_status={assessment_status}):\n\n{context}\n\n"
        "Synthesise the reproducibility risk-matrix core from the upstream outputs "
        "above. Cite evidence only from those outputs; for anything the upstream "
        "could not verify, leave it out of issues rather than inventing evidence.\n\n"
        'Return ONLY a single JSON object: {"risk_score": <int 0-100, higher means '
        'less reproducible>, "risk_level": "LOW|MEDIUM|HIGH|CRITICAL", "verdict": '
        '"ACCEPT|MINOR REVISION|MAJOR REVISION|REJECT", "issues": {"critical": [], '
        '"major": [], "minor": [], "suggestions": []}, "required_changes": []} — no '
        "prose, no markdown fences. Each issue is an object with id, description and "
        "an evidence file path under ai4r/<review_title>/."
    )


def _md_prompt(guidance: str, context: str, assessment_status: str) -> str:
    return (
        f"Upstream outputs (assessment_status={assessment_status}):\n\n{context}\n\n"
        f"Write {guidance}.\n"
        "Return the document as GitHub-flavoured Markdown only. Cite evidence by "
        "file path under ai4r/<review_title>/, and never invent results the "
        "upstream outputs do not contain."
    )


def _run_call(user: str, model: str, complete_fn: CompleteFn | None) -> str:
    kwargs: dict[str, Any] = {
        "system": load_skill("review/SKILL.md"),
        "user": user,
        "model": model,
        "tools": (),
        "max_steps": 1,
    }
    if complete_fn is not None:
        kwargs["complete_fn"] = complete_fn
    return run_agent(**kwargs)


def _normalise_core(core: dict[str, Any]) -> dict[str, Any]:
    verdict = core.get("verdict")
    verdict = verdict if verdict in _VERDICTS else "MAJOR REVISION"

    score = core.get("risk_score")
    if not isinstance(score, int) or isinstance(score, bool):
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None

    level = core.get("risk_level")
    level = level if level in _RISK_LEVELS else None
    if score is None:
        score = _score_from_level(level) if level else 50
    score = max(0, min(100, score))
    if level is None:
        level = _level_from_score(score)

    issues = core.get("issues")
    issues = issues if isinstance(issues, dict) else {}
    norm_issues = {
        key: (issues.get(key) if isinstance(issues.get(key), list) else [])
        for key in ("critical", "major", "minor", "suggestions")
    }
    required = core.get("required_changes")
    return {
        "risk_score": score,
        "risk_level": level,
        "verdict": verdict,
        "issues": norm_issues,
        "required_changes": required if isinstance(required, list) else [],
    }


def _assemble(
    review_title: str,
    paper_title: str | None,
    assessment_status: str,
    upstream_status: dict[str, Any],
    core: dict[str, Any] | None,
    failure_mode: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    rm: dict[str, Any] = {
        "paper_id": review_title,
        "paper_title": paper_title,
        "assessed_at": now_iso(),
        "assessment_status": assessment_status,
        "upstream_status": upstream_status,
    }
    if assessment_status == "failed":
        rm.update(
            {
                "risk_score": None,
                "risk_level": None,
                "verdict": "UNABLE_TO_ASSESS",
                "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
                "required_changes": [],
                "failure_mode": failure_mode,
                "failure_reason": failure_reason,
            }
        )
    else:
        rm.update(core or {})
    return rm


def _failed_md(rm: dict[str, Any]) -> dict[str, str]:
    body = (
        f"# Review — {rm['assessment_status']}\n\n"
        f"Verdict: **{rm['verdict']}**\n\n"
        "This audit could not be completed.\n\n"
        f"- failure_mode: {rm.get('failure_mode')}\n"
        f"- reason: {rm.get('failure_reason')}\n\n"
        f"Upstream status: `{json.dumps(rm['upstream_status'])}`\n"
    )
    return dict.fromkeys(_MD_OUTPUTS, body)


def _write_review(review_dir: Path, risk_matrix: dict[str, Any], md_files: dict[str, str]) -> None:
    rdir = review_dir / "review"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "risk_matrix.json").write_text(
        json.dumps(risk_matrix, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for name in _MD_OUTPUTS:  # every markdown file must exist
        text = md_files.get(name) or f"# {name}\n"
        (rdir / name).write_text(text, encoding="utf-8")

    append_log(
        review_dir,
        f"REVIEW assessment_status={risk_matrix['assessment_status']} "
        f"verdict={risk_matrix['verdict']}",
    )


def run_review(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
) -> dict[str, Any]:
    """Run the Review stage for ``review_title``; return the risk_matrix dict."""
    review_dir = Path(root) / "ai4r" / review_title
    unknown = {"kbe": {"status": "unknown"}, "cqv": {"status": "unknown"}, "er": {"status": "skipped"}}

    if not is_kebab(review_title):
        rm = _assemble(
            review_title, None, "failed", unknown, None,
            "parse_error", f"review_title is not kebab-case: {review_title!r}",
        )
        _write_review(review_dir, rm, _failed_md(rm))
        return rm

    kbe, kbe_status = _load_upstream(review_dir / "kbe" / "kbe_output.json")
    cqv, cqv_status = _load_upstream(review_dir / "cqv" / "cqv_output.json")
    er, er_status = _load_upstream(review_dir / "er" / "er_output.json")
    if er is None:
        er_status = "skipped"

    upstream_status = {
        "kbe": _status_entry(kbe, kbe_status),
        "cqv": _status_entry(cqv, cqv_status),
        "er": {"status": er_status},
    }
    title = kbe.get("paper_title") if isinstance(kbe, dict) else None
    paper_title = title if isinstance(title, str) and title else None

    if kbe_status in _FAILED_STATUSES and cqv_status in _FAILED_STATUSES:
        rm = _assemble(
            review_title, paper_title, "failed", upstream_status, None,
            "all_upstream_failed", f"KBE: {kbe_status}; CQV: {cqv_status}",
        )
        _write_review(review_dir, rm, _failed_md(rm))
        return rm

    assessment_status = (
        "complete" if kbe_status == "success" and cqv_status == "success" else "partial"
    )
    context = _context_blob(kbe, cqv, er)
    model_name = model or model_for("review")

    try:
        core_raw = _run_call(_risk_prompt(context, assessment_status), model_name, complete_fn)
        core = _normalise_core(parse_json_object(core_raw))
    except Exception as exc:  # cannot produce a verdict -> failed, but still write 4 files
        rm = _assemble(
            review_title, paper_title, "failed", upstream_status, None,
            "risk_matrix_schema_error", f"risk-matrix synthesis failed: {exc}",
        )
        _write_review(review_dir, rm, _failed_md(rm))
        return rm

    rm = _assemble(review_title, paper_title, assessment_status, upstream_status, core)

    md_files: dict[str, str] = {}
    for filename, guidance in _MD_OUTPUTS.items():
        try:
            md_files[filename] = _run_call(
                _md_prompt(guidance, context, assessment_status), model_name, complete_fn
            )
        except Exception as exc:  # a markdown miss is degraded, not fatal — placeholder it
            md_files[filename] = (
                f"# {filename}\n\n_Generation failed: {exc}._\n\n"
                "See risk_matrix.json for the verdict.\n"
            )
    _write_review(review_dir, rm, md_files)
    return rm


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.review <review_title> [--root DIR]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the Review stage.")
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    parser.add_argument("--model", default=None, help="LiteLLM model override")
    args = parser.parse_args(argv)

    rm = run_review(args.review_title, root=args.root, model=args.model)
    print(
        f"REVIEW {rm['assessment_status']} verdict={rm['verdict']} "
        f"-> {args.root}/ai4r/{args.review_title}/review/"
    )
    return 0 if rm["assessment_status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
