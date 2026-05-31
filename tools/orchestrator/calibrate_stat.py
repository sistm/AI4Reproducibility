"""Calibration harness for the statistical-validity judges (dev tool).

Runs ONLY the CQV statistical-validity layer against a prepared review and
prints each judge's verdict next to the exact evidence it saw, so the seven
rubrics can be eyeballed and tuned on real code before trusting them in the
pipeline. This is a calibration utility, not a pipeline stage: it performs no
code audit and writes no files.

    python -m tools.orchestrator.calibrate_stat <review_title> [--root DIR] [--model M]

By default it uses the real model (configure via AI4R_MODEL_CQV or --model), so
the verdicts reflect production behaviour. It reads ``input/assets/`` for code
evidence and ``kbe/kbe_output.json`` (if present) for the two paper-context
judges — using the same evidence the pipeline would feed them
(:func:`tools.orchestrator.cqv._kbe_context`), so calibration is faithful.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.orchestrator.cqv import _kbe_context
from tools.orchestrator.llm import CompleteFn
from tools.orchestrator.stat_evidence import gather_stat_evidence
from tools.orchestrator.stat_judges import run_stat_judges

_RULE = "=" * 72


def format_calibration_report(
    evidence: Mapping[str, str],
    verdicts: Sequence[dict[str, Any]],
    *,
    max_evidence_chars: int = 1200,
) -> str:
    """Render verdicts beside the evidence each judge saw, for eyeballing."""
    out: list[str] = []
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
        ev = (evidence.get(v["item_id"], "") or "").strip()
        shown = ev if len(ev) <= max_evidence_chars else ev[:max_evidence_chars] + "\n  …(truncated)"
        out.append(_RULE)
        out.append(f"[{str(v['severity']).upper()}] {v['item_id']}  ({v['tool_id']})")
        out.append(f"verdict: {v['verdict'].upper()}   confidence: {v.get('confidence', '-')}")
        out.append(f"rationale: {v.get('rationale', '')}")
        refs = v.get("evidence_refs") or []
        if refs:
            out.append("evidence_refs: " + "; ".join(str(r) for r in refs))
        out.append("---- evidence the judge saw ----")
        out.append(shown if shown else "(none — judged not_applicable without a model call)")
    summary = ", ".join(f"{k}={n}" for k, n in sorted(counts.items()))
    out.append(_RULE)
    out.append(f"summary: {summary}")
    return "\n".join(out)


def run_calibration(
    review_title: str,
    *,
    root: Path | str = ".",
    model: str | None = None,
    complete_fn: CompleteFn | None = None,
) -> str:
    """Run the stat judges for ``review_title`` and return a printable report."""
    review_dir = Path(root) / "ai4r" / review_title
    assets_dir = review_dir / "input" / "assets"
    evidence = gather_stat_evidence(assets_dir)
    verdicts = run_stat_judges(
        evidence,
        kbe_context=_kbe_context(review_dir) or None,
        model=model,
        complete_fn=complete_fn,
    )
    return format_calibration_report(evidence, verdicts)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.calibrate_stat <review_title>``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Eyeball the statistical-validity judges against a prepared review."
    )
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    parser.add_argument("--model", default=None, help="LiteLLM model override for the judges")
    args = parser.parse_args(argv)

    print(run_calibration(args.review_title, root=args.root, model=args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
