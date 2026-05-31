"""Top-level pipeline orchestrator: chain the AI4R stages end-to-end.

``prepare_review.sh`` -> KBE -> CQV -> (ER skipped stub) -> Review ->
``validate_review.sh``, exposed as::

    python -m tools.orchestrator.run <review_title> [--root DIR] [--model M]

This driver is the production entry point the per-stage runners
(:mod:`tools.orchestrator.kbe`, :mod:`~tools.orchestrator.cqv`,
:mod:`~tools.orchestrator.review`) were building toward. It owns only the
cross-stage glue; each stage still owns its own contract and never raises
(LOGIC.md §6), so the pipeline records a degraded summary rather than aborting
when a stage reports failure. Review already degrades gracefully on
failed/partial upstream, and ``validate_review.sh`` checks only that every
contract file exists and is well-formed — so a degraded run still produces a
complete, gate-passing artifact set.

Pre-flight and post-flight stay in the existing bash scripts
(``prepare_review.sh`` / ``validate_review.sh``) rather than being
reimplemented here: they are the source of truth for the directory contract and
the output gate (LOGIC.md §2), they are already bash-3.2 safe, and shelling out
keeps a single definition of each (no Python/bash drift). Both compute
``REVIEW_DIR`` from ``$(pwd)/ai4r/<title>``, so they are invoked with
``cwd=<root>``.

ER is deferred (LOGIC.md §3.3): nothing executes submission code in v0, so the
pipeline writes the reserved skipped stub ``er/er_output.json``
(``{"status": "skipped", ...}``) itself. Without it the post-flight gate cannot
pass even when every other stage succeeds, because ``validate_review.sh``
requires ``er/er_output.json`` (file presence + a ``status`` key) and Review
reads it as upstream context.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.orchestrator.cqv import run_cqv
from tools.orchestrator.kbe import run_kbe
from tools.orchestrator.llm import CompleteFn
from tools.orchestrator.review import run_review

# The pre/post-flight scripts live at the repo root (not packaged). Resolve
# them relative to this file so the entry point works regardless of cwd:
# tools/orchestrator/run.py -> parents[2] == repo root. With an editable
# install (`pip install -e .`) __file__ still points into the repo.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PREPARE_SCRIPT = "prepare_review.sh"
_VALIDATE_SCRIPT = "validate_review.sh"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _run_script(name: str, review_title: str, root: Path | str) -> tuple[int, str]:
    """Run a pre/post-flight bash script; return (exit_code, combined output).

    Never raises: a missing script or missing ``bash`` is reported as a
    non-zero code so the caller can fold it into the run summary rather than
    crash. The script is given ``review_title`` as its only argument and run
    with ``cwd=root`` (both scripts derive REVIEW_DIR from ``$(pwd)``).
    """
    script = _REPO_ROOT / name
    if not script.is_file():
        return 127, f"script not found: {script}"
    bash = shutil.which("bash")
    if bash is None:
        return 127, "bash not found on PATH (pre/post-flight scripts need it)"
    proc = subprocess.run(
        [bash, str(script), review_title],
        cwd=str(Path(root).resolve()),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _write_er_stub(review_dir: Path, review_title: str) -> dict[str, Any]:
    """Write the reserved skipped ER stub (LOGIC.md §3.3) and log it.

    ER never runs in v0; this stub satisfies ``validate_review.sh`` (which
    requires ``er/er_output.json`` with a ``status`` key) and gives Review a
    well-formed upstream input. ``skipped`` is the status enum value reserved
    for exactly this (LOGIC.md §5; conventions §8).
    """
    er_dir = review_dir / "er"
    er_dir.mkdir(parents=True, exist_ok=True)
    stub: dict[str, Any] = {
        "status": "skipped",
        "paper_id": review_title,
        "skipped_at": _now(),
        "reason": "ER stage deferred in v0 (LOGIC.md §3.3): no code is executed.",
    }
    (er_dir / "er_output.json").write_text(
        json.dumps(stub, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logs = review_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "workflow.log").open("a", encoding="utf-8") as log:
        log.write(f"{_now()} ER status=skipped (deferred, v0)\n")
    return stub


def _tail(text: str, n: int = 8) -> list[str]:
    """Last ``n`` non-empty lines of script output, for compact summaries."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-n:]


def run_pipeline(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
    extract_fn: Callable[[Path], str] | None = None,
    run_prepare: bool = True,
    run_validate: bool = True,
) -> dict[str, Any]:
    """Run the full pipeline for ``review_title``; return a result summary.

    ``model``, when given, overrides the model for *every* stage; when ``None``
    each stage resolves its own model via ``config.model_for(stage)`` (honouring
    the ``AI4R_MODEL_<STAGE>`` env overrides). ``complete_fn`` / ``extract_fn``
    are injectable seams for testing without a live model or PDF backend.

    The summary always carries ``ok`` (True iff the post-flight gate passed, or
    ``None`` when post-flight is skipped), a per-step record, and timestamps.
    A failed pre-flight is the only hard stop: without the input layout / PDF
    there is nothing downstream to run.
    """
    review_dir = Path(root) / "ai4r" / review_title
    summary: dict[str, Any] = {
        "review_title": review_title,
        "root": str(root),
        "started_at": _now(),
        "steps": {},
    }
    steps: dict[str, Any] = summary["steps"]

    # --- pre-flight (hard gate: no PDF/layout -> nothing to do) -------------
    if run_prepare:
        code, out = _run_script(_PREPARE_SCRIPT, review_title, root)
        steps["prepare"] = {"exit_code": code}
        if code != 0:
            steps["prepare"]["output"] = _tail(out)
            summary["ok"] = False
            summary["failed_at"] = "prepare"
            summary["ended_at"] = _now()
            return summary

    # --- KBE -> CQV (each owns its contract; neither aborts the chain) ------
    kbe = run_kbe(
        review_title, root=root, model=model, complete_fn=complete_fn, extract_fn=extract_fn
    )
    steps["kbe"] = {"status": kbe.get("status"), "failure_mode": kbe.get("failure_mode")}

    cqv = run_cqv(review_title, root=root, model=model, complete_fn=complete_fn)
    steps["cqv"] = {"status": cqv.get("status"), "failure_mode": cqv.get("failure_mode")}

    # --- ER: deferred, write the skipped stub the gate + Review require -----
    er = _write_er_stub(review_dir, review_title)
    steps["er"] = {"status": er["status"]}

    # --- Review (synthesis; degrades on failed/partial upstream) ------------
    rm = run_review(review_title, root=root, model=model, complete_fn=complete_fn)
    steps["review"] = {
        "assessment_status": rm.get("assessment_status"),
        "verdict": rm.get("verdict"),
    }

    # --- post-flight gate ---------------------------------------------------
    if run_validate:
        code, out = _run_script(_VALIDATE_SCRIPT, review_title, root)
        steps["validate"] = {"exit_code": code}
        if code != 0:
            steps["validate"]["output"] = _tail(out)
        summary["ok"] = code == 0
    else:
        summary["ok"] = None

    summary["ended_at"] = _now()
    return summary


def _print_summary(summary: dict[str, Any], root: str, review_title: str) -> None:
    steps = summary.get("steps", {})

    def line(label: str, value: str) -> None:
        print(f"  {label:<9} {value}")

    print(f"pipeline: {review_title}")
    if "prepare" in steps:
        line("prepare", f"exit {steps['prepare']['exit_code']}")
    if "kbe" in steps:
        line("KBE", str(steps["kbe"].get("status")))
    if "cqv" in steps:
        line("CQV", str(steps["cqv"].get("status")))
    if "er" in steps:
        line("ER", str(steps["er"].get("status")))
    if "review" in steps:
        rv = steps["review"]
        line("Review", f"{rv.get('assessment_status')} verdict={rv.get('verdict')}")
    if "validate" in steps:
        line("validate", f"exit {steps['validate']['exit_code']}")

    ok = summary.get("ok")
    overall = "PASS" if ok else ("SKIPPED" if ok is None else "FAIL")
    where = f"{root}/ai4r/{review_title}/"
    print(f"result: {overall}  -> {where}")
    if summary.get("failed_at"):
        print(f"  stopped at: {summary['failed_at']}")


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.run <review_title> [--root DIR]``."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m tools.orchestrator.run",
        description="Run the full AI4R reproducibility pipeline end-to-end "
        "(prepare -> KBE -> CQV -> ER[skipped] -> Review -> validate).",
    )
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    parser.add_argument(
        "--model",
        default=None,
        help="LiteLLM model string applied to EVERY stage; omit to use the "
        "per-stage config defaults / AI4R_MODEL_<STAGE> env overrides.",
    )
    args = parser.parse_args(argv)

    summary = run_pipeline(args.review_title, root=args.root, model=args.model)
    _print_summary(summary, args.root, args.review_title)
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
