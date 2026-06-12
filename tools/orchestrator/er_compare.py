"""ER output comparison (LOGIC.md §6).

Three comparison strategies, each producing a ComparisonResult:

  * Figures: perceptual-hash (pHash) gate. If the Hamming distance between the
    reproduced figure and the manuscript figure is below threshold, pass
    without an LLM call. Otherwise escalate to an LLM visual comparison that
    classifies the mismatch as cosmetic or substantive.

  * Tables: numerical comparison with relative tolerance. No image involved.

  * Numerical plot data (scatter/line): when the reproduced run exposes the
    underlying coordinates (e.g. a saved .rds), compare numerically — the most
    defensible evidence for a reviewer.

Pixel hashing is deliberately NOT used: different GPU drivers, font renderers,
and graphics backends produce pixel-different output for numerically identical
plots, so it would false-fail constantly. See LOGIC.md §6.

The pHash implementation here is dependency-light: it uses Pillow if available
and degrades to status "unverified" when it is not, so the module imports
cleanly in CI without image libraries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# pHash escalation threshold (Hamming distance over a 64-bit hash). Below this,
# treat as a match. ~10 is a conservative starting point; calibrate against
# real figures from the reference paper once ER runs end to end.
DEFAULT_PHASH_THRESHOLD = 10

# Relative tolerance for numerical (table / plot-data) comparison.
DEFAULT_NUMERIC_RTOL = 0.01


@dataclass
class ComparisonResult:
    """Outcome of comparing one reproduced artifact against its reference.

    ``needs_visual_review`` is set True when pHash is over threshold (or hashing
    is unavailable). ER never calls the LLM to adjudicate this — that judgment
    belongs in Review/Critique, which has the paper context required to decide
    whether the difference is cosmetic or substantive (LOGIC.md §6).
    """

    artifact: str
    kind: str                       # "figure" | "table" | "plot_data"
    status: str                     # "pass" | "mismatch_flagged" | "fail" | "unverified"
    method: str                     # "phash" | "numeric" | "none"
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    needs_visual_review: bool = False   # Review/Critique should call LLM vision model

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "kind": self.kind,
            "status": self.status,
            "method": self.method,
            "detail": self.detail,
            "metadata": self.metadata,
            "needs_visual_review": self.needs_visual_review,
        }


# ---------------------------------------------------------------------------
# Perceptual hashing (Pillow-optional)
# ---------------------------------------------------------------------------

def _phash(image_path: Path) -> int | None:
    """Compute a 64-bit perceptual hash (dHash variant). None if unavailable.

    dHash: resize to 9x8 greyscale, compare adjacent pixels row-wise. Robust to
    scaling, brightness, and minor rendering differences; sensitive to genuine
    structural change.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("L").resize((9, 8))
    except (OSError, ValueError):
        return None
    bits = 0
    pos = 0
    for row in range(8):
        for col in range(8):
            left = img.getpixel((col, row))
            right = img.getpixel((col + 1, row))
            if left > right:
                bits |= (1 << pos)
            pos += 1
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------------------
# Figure comparison: pHash gate -> LLM escalation
# ---------------------------------------------------------------------------

# Type alias for the LLM visual-comparison seam. Tests inject a fake; the real
# implementation would send both images to a vision model.
def compare_figure(
    reproduced: Path,
    reference: Path,
    *,
    threshold: int = DEFAULT_PHASH_THRESHOLD,
    llm_compare_fn: Any | None = None,
) -> ComparisonResult:
    """Compare a reproduced figure against the manuscript reference.

    Stage 1 — pHash gate (always run by ER): below threshold → pass.
    Stage 2 — LLM visual adjudication (called by Review/Critique, not ER):
      only runs when ``llm_compare_fn`` is provided. ER never passes this;
      the model needs paper context to decide cosmetic vs substantive, and
      that context lives in Review (LOGIC.md §6).

    When pHash is over threshold and no LLM is provided, the result is
    ``status="mismatch_flagged", needs_visual_review=True`` — a signal for
    Review/Critique to call the LLM with full manuscript context.
    """
    artifact = reproduced.name

    h_repro = _phash(reproduced)
    h_ref = _phash(reference)

    if h_repro is not None and h_ref is not None:
        distance = _hamming(h_repro, h_ref)
        if distance <= threshold:
            return ComparisonResult(
                artifact=artifact, kind="figure", status="pass", method="phash",
                detail=f"pHash Hamming distance {distance} \u2264 {threshold}.",
                metadata={"hamming_distance": distance, "threshold": threshold},
            )
        # Over threshold — escalate to LLM only if a comparator is provided
        # (i.e. called from Review/Critique, not ER).
        if llm_compare_fn is not None:
            return _escalate_figure(artifact, reproduced, reference, distance, llm_compare_fn)
        return ComparisonResult(
            artifact=artifact, kind="figure", status="mismatch_flagged", method="phash",
            detail=(
                f"pHash Hamming distance {distance} > {threshold}; "
                "flagged for visual review."
            ),
            metadata={"hamming_distance": distance, "threshold": threshold},
            needs_visual_review=True,
        )

    # Hashing unavailable on one/both sides (Pillow absent or unreadable image).
    if llm_compare_fn is not None:
        return _escalate_figure(artifact, reproduced, reference, None, llm_compare_fn)
    return ComparisonResult(
        artifact=artifact, kind="figure", status="mismatch_flagged", method="none",
        detail="Perceptual hashing unavailable; flagged for visual review.",
        needs_visual_review=True,
    )


def _escalate_figure(
    artifact: str,
    reproduced: Path,
    reference: Path,
    distance: int | None,
    llm_compare_fn: Any,
) -> ComparisonResult:
    try:
        verdict = llm_compare_fn(reproduced, reference)
    except Exception as exc:
        return ComparisonResult(
            artifact=artifact, kind="figure", status="unverified", method="phash+llm",
            detail=f"LLM visual comparison failed: {exc}",
            metadata={"hamming_distance": distance},
        )

    classification = str(verdict.get("classification", "")).lower()
    detail = str(verdict.get("detail", ""))
    status = "pass" if classification == "cosmetic" else "fail"
    return ComparisonResult(
        artifact=artifact, kind="figure", status=status, method="phash+llm",
        detail=f"LLM classified mismatch as {classification or 'unknown'}: {detail}",
        metadata={"hamming_distance": distance, "classification": classification},
    )


# ---------------------------------------------------------------------------
# Numerical comparison: tables and plot data
# ---------------------------------------------------------------------------

def compare_numeric(
    artifact: str,
    reproduced: list[list[float]],
    reference: list[list[float]],
    *,
    kind: str = "table",
    rtol: float = DEFAULT_NUMERIC_RTOL,
) -> ComparisonResult:
    """Compare two numeric grids with relative tolerance.

    Shapes must match. Each cell passes if |a - b| <= rtol * max(|a|, |b|, eps).
    Returns the worst-case relative error in metadata for the reviewer.
    """
    if len(reproduced) != len(reference) or any(
        len(r1) != len(r2) for r1, r2 in zip(reproduced, reference, strict=False)
    ):
        return ComparisonResult(
            artifact=artifact, kind=kind, status="fail", method="numeric",
            detail=(
                f"Shape mismatch: reproduced {_shape(reproduced)} vs "
                f"reference {_shape(reference)}."
            ),
        )

    eps = 1e-12
    worst = 0.0
    n_fail = 0
    for r1, r2 in zip(reproduced, reference, strict=False):
        for a, b in zip(r1, r2, strict=False):
            denom = max(abs(a), abs(b), eps)
            rel = abs(a - b) / denom
            worst = max(worst, rel)
            if rel > rtol:
                n_fail += 1

    if n_fail == 0:
        return ComparisonResult(
            artifact=artifact, kind=kind, status="pass", method="numeric",
            detail=f"All cells within rtol={rtol}; worst relative error {worst:.2e}.",
            metadata={"worst_rel_error": worst, "rtol": rtol},
        )
    return ComparisonResult(
        artifact=artifact, kind=kind, status="fail", method="numeric",
        detail=(
            f"{n_fail} cell(s) exceed rtol={rtol}; worst relative error "
            f"{worst:.2e}."
        ),
        metadata={"worst_rel_error": worst, "rtol": rtol, "cells_failed": n_fail},
    )


def _shape(grid: list[list[float]]) -> str:
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    return f"{rows}x{cols}"
