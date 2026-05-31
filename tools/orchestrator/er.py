"""ER stage runner: write the reserved skipped ER stub (LOGIC.md §3.3).

ER (Experimental Run) is the only stage that would execute submission code, in
a Docker container with reduced runtime parameters. It is deferred in v0:
nothing is executed, so this stage simply writes ``er/er_output.json`` with the
reserved ``skipped`` status and logs it. The stub is not cosmetic —
``validate_review.sh`` requires ``er/er_output.json`` (file presence + a
``status`` key) and Review reads it as upstream context, so without it the
post-flight gate cannot pass even when every other stage succeeds.

This mirrors the KBE/CQV/Review stage shape (``run_<stage>(...) -> dict``, never
raises, the orchestrator owns ``paper_id``, writes the contract file plus a
``workflow.log`` line) so the four stages are symmetric. When ER is implemented
(§5h) the Docker run will live here; the output contract (writing
``er/er_output.json``) stays the same.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_er(review_title: str, *, root: Path | str = ".") -> dict[str, Any]:
    """Write the skipped ER stub for ``review_title`` and return it.

    v0 executes no code, so the status is always ``skipped`` (the enum value
    reserved for ER; conventions §8). Takes no model or completion seam because
    nothing calls a model. Never raises.
    """
    review_dir = Path(root) / "ai4r" / review_title
    er_dir = review_dir / "er"
    er_dir.mkdir(parents=True, exist_ok=True)

    output: dict[str, Any] = {
        "status": "skipped",
        "paper_id": review_title,
        "skipped_at": _now(),
        "reason": "ER stage deferred in v0 (LOGIC.md §3.3): no code is executed.",
    }
    (er_dir / "er_output.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logs_dir = review_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / "workflow.log").open("a", encoding="utf-8") as log:
        log.write(f"{_now()} ER status=skipped (deferred, v0)\n")
    return output


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m tools.orchestrator.er <review_title> [--root DIR]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Write the skipped ER stub (v0).")
    parser.add_argument("review_title", help="kebab-case review identifier")
    parser.add_argument("--root", default=".", help="directory containing ai4r/")
    args = parser.parse_args(argv)

    output = run_er(args.review_title, root=args.root)
    print(f"ER {output['status']} -> {args.root}/ai4r/{args.review_title}/er/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
