"""ER stage runner: execute the submission and compare outputs (LOGIC.md §3.3, §6).

ER is the only stage that runs submission code. The flow:

  1. Guard the assets directory (same as CQV).
  2. README pre-flight (er_preflight): one LLM call decides the execution mode.
     Two skip outcomes (no runtime docs / no intermediate docs) are major-
     revision signals surfaced as checklist_flags; ER does not execute in those
     cases.
  3. Resolve the execution environment: read execution_environment from
     cqv_output.json if present, else parse renv.lock directly. No lockfile is
     a skip (skipped_no_data).
  4. Execute in Docker (er_docker), behind an injectable run_fn seam so this
     stage is fully testable without Docker.
  5. Compare produced artifacts against references (er_compare) — pHash gate
     with LLM escalation for figures, numerical tolerance for tables.
  6. Write er/er_output.json. The contract the validator and Review depend on
     is unchanged: a `status` key is always present.

Never raises. Like the other stages: run_er(...) -> dict, orchestrator owns
paper_id, writes the contract file plus a workflow.log line.

Backward compatibility: run_er(review_title, *, root=".") still works and, with
no model/complete_fn and no Docker, lands on a skip status with a populated
er_output.json — the validator and Review still pass.
"""

from __future__ import annotations

import json

# Default execution budget: a few hours. Override with AI4R_ER_TIMEOUT_SECONDS.
import os
from pathlib import Path
from typing import Any

from tools.orchestrator._stage import append_log, now_iso
from tools.orchestrator.er_artifacts import new_files_since, pair_and_compare, snapshot_files
from tools.orchestrator.er_compare import ComparisonResult
from tools.orchestrator.er_docker import (
    RunFn,
    image_for_r_version,
    restore_and_run,
)
from tools.orchestrator.er_preflight import (
    PreflightAssessment,
    assess_readme,
)
from tools.orchestrator.llm import CompleteFn

DEFAULT_BUDGET_SECONDS = int(os.environ.get("AI4R_ER_TIMEOUT_SECONDS", str(3 * 60 * 60)))
DEFAULT_PER_SCRIPT_TIMEOUT = int(
    os.environ.get("AI4R_ER_PER_SCRIPT_TIMEOUT_SECONDS", str(30 * 60))
)


def _execution_environment(review_dir: Path, assets_dir: Path) -> dict[str, Any]:
    """Resolve the execution environment.

    Prefer cqv_output.execution_environment (written by CQV); fall back to
    parsing renv.lock directly so ER is self-sufficient if CQV did not populate
    it.
    """
    cqv_path = review_dir / "cqv" / "cqv_output.json"
    try:
        cqv = json.loads(cqv_path.read_text(encoding="utf-8"))
        env = cqv.get("execution_environment")
        if isinstance(env, dict) and env.get("lockfile_present"):
            return env
    except (OSError, ValueError):
        pass
    return _parse_renv_lock(assets_dir)


def _parse_renv_lock(assets_dir: Path) -> dict[str, Any]:
    """Parse renv.lock for R version and package list (no LLM)."""
    lockfile = None
    for p in assets_dir.rglob("renv.lock"):
        if p.is_file():
            lockfile = p
            break
    if lockfile is None:
        return {"lockfile_present": False}
    try:
        data = json.loads(lockfile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"lockfile_present": True, "parse_error": True}
    return {
        "lockfile_present": True,
        "r_version": (data.get("R") or {}).get("Version"),
        "packages": {
            name: (pkg or {}).get("Version")
            for name, pkg in (data.get("Packages") or {}).items()
        },
    }


def _entry_command(review_dir: Path) -> list[str]:
    """Determine the main entry point from CQV's check_main_entry_point result.

    Falls back to a conventional 'main.R' if CQV did not identify one.
    """
    cqv_path = review_dir / "cqv" / "cqv_output.json"
    try:
        cqv = json.loads(cqv_path.read_text(encoding="utf-8"))
        pd = cqv.get("partial_data") or {}
        entry = pd.get("main_entry_point")
        if isinstance(entry, str) and entry.strip():
            return ["Rscript", entry.strip()]
    except (OSError, ValueError):
        pass
    return ["Rscript", "main.R"]


def _load_targets(review_dir: Path) -> list[dict[str, Any]]:
    """Read reproduction_targets from kbe_output.json. Returns [] on any failure."""
    try:
        kbe = json.loads((review_dir / "kbe" / "kbe_output.json").read_text(encoding="utf-8"))
        targets = kbe.get("reproduction_targets")
        return targets if isinstance(targets, list) else []
    except (OSError, ValueError):
        return []


def _kbe_dir(review_dir: Path) -> Path:
    return review_dir / "kbe"


def _skip_output(
    review_title: str,
    status: str,
    assessment: PreflightAssessment | None,
    *,
    reason: str,
    execution_environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a skipped er_output dict (no execution happened)."""
    out: dict[str, Any] = {
        "status": status,
        "paper_id": review_title,
        "skipped_at": now_iso(),
        "reason": reason,
        "checklist_flags": assessment.checklist_flags if assessment else [],
        "execution_mode": assessment.execution_mode if assessment else status,
    }
    if assessment is not None:
        out["preflight"] = assessment.to_dict()
    if execution_environment is not None:
        out["execution_environment"] = execution_environment
    return out


def _write(review_dir: Path, output: dict[str, Any]) -> None:
    er_dir = review_dir / "er"
    er_dir.mkdir(parents=True, exist_ok=True)
    (er_dir / "er_output.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_log(
        review_dir,
        f"ER status={output['status']} mode={output.get('execution_mode', '-')}",
    )


def run_er(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
    run_fn: RunFn | None = None,
    budget_seconds: int = DEFAULT_BUDGET_SECONDS,
    enabled: bool = False,
) -> dict[str, Any]:
    """Run the ER stage for ``review_title`` and return the written output dict.

    ``enabled`` defaults to False: without it, ER preserves the v0 skipped-stub
    behaviour so existing pipelines are unchanged. Set enabled=True (or provide
    a run_fn for tests) to exercise the pre-flight + execution path.

    Never raises.
    """
    review_dir = Path(root) / "ai4r" / review_title
    assets_dir = review_dir / "input" / "assets"

    # v0 default: skipped stub (unchanged contract) unless explicitly enabled.
    if not enabled and run_fn is None:
        output = {
            "status": "skipped",
            "paper_id": review_title,
            "skipped_at": now_iso(),
            "reason": "ER stage not enabled (pass enabled=True to execute).",
            "checklist_flags": [],
            "execution_mode": "skipped",
        }
        _write(review_dir, output)
        return output

    # Assets guard.
    if not assets_dir.is_dir() or not any(p.is_file() for p in assets_dir.rglob("*")):
        output = _skip_output(
            review_title, "skipped_no_data", None,
            reason=f"no files found under {assets_dir}",
        )
        _write(review_dir, output)
        return output

    # README pre-flight.
    assessment = assess_readme(
        assets_dir, budget_seconds=budget_seconds, model=model, complete_fn=complete_fn,
    )
    if not assessment.will_execute:
        output = _skip_output(
            review_title, assessment.execution_mode, assessment,
            reason=assessment.rationale,
        )
        _write(review_dir, output)
        return output

    # Resolve environment; no lockfile -> skip.
    env = _execution_environment(review_dir, assets_dir)
    if not env.get("lockfile_present"):
        output = _skip_output(
            review_title, "skipped_no_data", assessment,
            reason="No renv.lock found; cannot reconstruct the environment.",
            execution_environment=env,
        )
        _write(review_dir, output)
        return output

    image = image_for_r_version(env.get("r_version"))
    entry = _entry_command(review_dir)

    # Snapshot workspace before execution so we know exactly what was produced.
    before_snapshot = snapshot_files(assets_dir)

    restore, run = restore_and_run(
        assets_dir, image, entry,
        run_timeout=budget_seconds,
        restore_timeout=DEFAULT_PER_SCRIPT_TIMEOUT,
        run_fn=run_fn,
    )

    if not restore.ok:
        output = {
            "status": "failed",
            "paper_id": review_title,
            "assessed_at": now_iso(),
            "execution_mode": assessment.execution_mode,
            "checklist_flags": assessment.checklist_flags,
            "preflight": assessment.to_dict(),
            "execution_environment": env,
            "failure_mode": "renv_restore_failed",
            "reason": "renv::restore() did not complete; environment incomplete.",
            "restore_log": _tail(restore.stderr or restore.stdout),
        }
        _write(review_dir, output)
        return output

    # Collect produced artifacts (files that did not exist before the run).
    produced = new_files_since(assets_dir, before_snapshot)

    run_ok = run is not None and run.ok
    output: dict[str, Any] = {
        "status": "success" if run_ok else "failed",
        "paper_id": review_title,
        "assessed_at": now_iso(),
        "execution_mode": assessment.execution_mode,
        "checklist_flags": assessment.checklist_flags,
        "preflight": assessment.to_dict(),
        "execution_environment": env,
        "image": image,
        "entry_command": entry,
        "run": {
            "returncode": run.returncode if run else None,
            "timed_out": run.timed_out if run else None,
            "stdout_tail": _tail(run.stdout) if run else "",
            "stderr_tail": _tail(run.stderr) if run else "",
            "artifacts": [str(p.relative_to(assets_dir)) for p in produced],
        },
        "comparisons": [],
    }
    if not run_ok and run is not None and run.timed_out:
        output["failure_mode"] = "execution_timeout"
    elif not run_ok:
        output["failure_mode"] = "execution_error"

    # Pair targets against produced artifacts and run deterministic comparisons.
    # This runs even when the execution failed — partial output is still evidence.
    targets = _load_targets(review_dir)
    if targets:
        comparison_results = pair_and_compare(
            targets, produced, _kbe_dir(review_dir),
        )
        output["comparisons"] = [r.to_dict() for r in comparison_results]
        # Surface a checklist flag when any target produced nothing.
        missing = [r.artifact for r in comparison_results
                   if r.status == "no_artifact_produced"]
        if missing:
            output["checklist_flags"] = [
                *(output.get("checklist_flags") or []),
                "MISSING_REPRODUCED_ARTIFACTS",
            ]

    _write(review_dir, output)
    return output


_MAX_TAIL_CHARS = 4000


def _tail(text: str) -> str:
    if not text:
        return ""
    return text[-_MAX_TAIL_CHARS:]


def add_comparison(output: dict[str, Any], result: ComparisonResult) -> None:
    """Append a comparison result to an er_output dict (used by the comparison step)."""
    output.setdefault("comparisons", []).append(result.to_dict())


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.er <review_title> [--root DIR] [--enabled]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the ER stage.")
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    parser.add_argument("--model", default=None, help="LiteLLM model override")
    parser.add_argument("--enabled", action="store_true", help="actually execute (needs Docker)")
    args = parser.parse_args(argv)

    output = run_er(
        args.review_title, root=args.root, model=args.model, enabled=args.enabled,
    )
    print(f"ER {output['status']} -> {args.root}/ai4r/{args.review_title}/er/")
    return 0 if output["status"] in ("success", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
