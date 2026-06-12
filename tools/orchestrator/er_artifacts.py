"""ER artifact discovery and target-to-artifact pairing (LOGIC.md §3.3).

After the Docker run, the workspace contains both the original input files and
the newly produced outputs. This module handles three concerns:

  1. Snapshotting the workspace before execution so we can identify exactly
     which files were produced (not just which files exist).

  2. Classifying produced files by kind: figure (image), table (structured
     data), or numerical_result (text).

  3. Pairing each KBE reproduction_target with the best-matching produced
     artifact by filename heuristic, enabling ER to run a deterministic
     comparison (pHash for figures, numerical tolerance for tables).

Pairing is deliberately best-effort: an unmatched target gets
``status="no_artifact_produced"``, which is itself a strong reproducibility
finding. Ambiguous or unmatched cases are flagged for Review rather than
guessed at.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.orchestrator.er_compare import (
    DEFAULT_PHASH_THRESHOLD,
    ComparisonResult,
    compare_figure,
    compare_numeric,
)

# ---------------------------------------------------------------------------
# File-kind classification by extension
# ---------------------------------------------------------------------------

_FIGURE_EXTS = frozenset({".png", ".pdf", ".svg", ".eps", ".jpg", ".jpeg", ".tiff", ".tif"})
_TABLE_EXTS  = frozenset({".csv", ".tsv", ".json", ".rds", ".xlsx", ".xls"})
_TEXT_EXTS   = frozenset({".txt", ".md"})


def classify_artifact(path: Path) -> str:
    """Return ``"figure"``, ``"table"``, or ``"numerical_result"`` by extension."""
    ext = path.suffix.lower()
    if ext in _FIGURE_EXTS:
        return "figure"
    if ext in _TABLE_EXTS:
        return "table"
    return "numerical_result"


# ---------------------------------------------------------------------------
# Workspace snapshotting
# ---------------------------------------------------------------------------

def snapshot_files(directory: Path) -> frozenset[str]:
    """Record all relative file paths under *directory* (before execution)."""
    if not directory.is_dir():
        return frozenset()
    return frozenset(
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file()
    )


def new_files_since(directory: Path, before: frozenset[str]) -> list[Path]:
    """Return files added to *directory* since *before* snapshot, sorted."""
    if not directory.is_dir():
        return []
    after = frozenset(
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file()
    )
    return sorted(directory / rel for rel in after - before)


# ---------------------------------------------------------------------------
# Target-to-artifact matching
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase, strip punctuation and whitespace for fuzzy comparison."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _extract_numbers(text: str) -> list[str]:
    """Return all digit-sequences found in *text*."""
    return re.findall(r"\d+", text)


def _label_tokens(target: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (normalised_label, digit_list) for a target."""
    label = target.get("label") or target.get("id") or ""
    return _normalise(label), _extract_numbers(label)


def _filename_score(artifact_path: Path, norm_label: str, digits: list[str]) -> int:
    """Heuristic match score between a filename and a target label.

    Returns:
      2  — normalised label is a substring of normalised stem (strong)
      1  — all digits from the label appear in the stem (weak)
      0  — no match
    """
    stem = _normalise(artifact_path.stem)
    if norm_label and norm_label in stem:
        return 2
    if digits and all(d in stem for d in digits):
        return 1
    return 0


def match_target_to_artifacts(
    target: dict[str, Any],
    produced: list[Path],
) -> list[Path]:
    """Return produced artifacts that plausibly match *target*, best-first.

    Filters by kind first (figure extensions → figure targets, etc.), then
    ranks by filename heuristic.  Returns [] when nothing matches.
    """
    kind = target.get("kind", "numerical_result")
    norm_label, digits = _label_tokens(target)

    # Kind filter: only consider files of the matching type.
    candidates = [p for p in produced if classify_artifact(p) == kind]

    # Score each candidate; keep those with score > 0, sorted descending.
    scored = [(p, _filename_score(p, norm_label, digits)) for p in candidates]
    scored = [(p, s) for p, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored]


# ---------------------------------------------------------------------------
# Reference path resolution
# ---------------------------------------------------------------------------

def resolve_reference(
    target: dict[str, Any],
    kbe_dir: Path,
) -> Path | None:
    """Resolve the reference artifact path for a target.

    ``target["reference_path"]`` is stored relative to kbe_dir (e.g.
    ``"references/figure-3.png"``).  Returns None when the field is absent
    or the file does not exist on disk.
    """
    ref_rel = target.get("reference_path")
    if not isinstance(ref_rel, str) or not ref_rel.strip():
        return None
    ref_full = kbe_dir / ref_rel
    return ref_full if ref_full.is_file() else None


# ---------------------------------------------------------------------------
# Comparison dispatch
# ---------------------------------------------------------------------------

def _compare_one(
    target: dict[str, Any],
    produced_path: Path,
    reference_path: Path,
    *,
    phash_threshold: int = DEFAULT_PHASH_THRESHOLD,
) -> ComparisonResult:
    """Run the appropriate deterministic comparison for this target kind."""
    kind = target.get("kind", "numerical_result")

    if kind == "figure":
        return compare_figure(
            produced_path, reference_path,
            threshold=phash_threshold,
            llm_compare_fn=None,   # ER never calls the LLM; Review/Critique does
        )

    if kind == "table":
        # Try to load both as numeric grids for tolerance comparison.
        # Falls back to a binary file-equality check when parsing fails.
        try:
            repro_grid = _load_numeric_grid(produced_path)
            ref_grid   = _load_numeric_grid(reference_path)
            return compare_numeric(
                target.get("id", produced_path.name),
                repro_grid, ref_grid,
                kind="table",
            )
        except Exception as exc:
            # Can't parse as numbers — flag for visual review.
            return ComparisonResult(
                artifact=produced_path.name,
                kind="table",
                status="mismatch_flagged",
                method="none",
                detail=f"Could not parse table as numeric grid: {exc}",
                needs_visual_review=True,
            )

    # numerical_result: text-file comparison (exact after whitespace normalisation).
    try:
        repro_text = produced_path.read_text(encoding="utf-8", errors="replace").strip()
        ref_text   = reference_path.read_text(encoding="utf-8", errors="replace").strip()
        # Normalise whitespace for comparison.
        repro_norm = re.sub(r"\s+", " ", repro_text)
        ref_norm   = re.sub(r"\s+", " ", ref_text)
        status = "pass" if repro_norm == ref_norm else "mismatch_flagged"
        return ComparisonResult(
            artifact=produced_path.name,
            kind="numerical_result",
            status=status,
            method="text",
            detail="Text content matches after whitespace normalisation."
            if status == "pass"
            else "Text content differs; flagged for review.",
            needs_visual_review=(status == "mismatch_flagged"),
        )
    except Exception as exc:
        return ComparisonResult(
            artifact=produced_path.name,
            kind="numerical_result",
            status="mismatch_flagged",
            method="none",
            detail=f"Could not read text for comparison: {exc}",
            needs_visual_review=True,
        )


def _load_numeric_grid(path: Path) -> list[list[float]]:
    """Load a CSV/TSV as a list-of-lists of floats.

    Raises ValueError when the file cannot be parsed numerically.
    """
    import csv

    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    rows: list[list[float]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        for row in reader:
            numeric: list[float] = []
            for cell in row:
                cell = cell.strip()
                if not cell:
                    continue
                try:
                    numeric.append(float(cell))
                except ValueError:
                    pass  # skip header cells or non-numeric columns
            if numeric:
                rows.append(numeric)
    if not rows:
        raise ValueError("no numeric data found")
    return rows


# ---------------------------------------------------------------------------
# Top-level: pair all targets and run comparisons
# ---------------------------------------------------------------------------

def pair_and_compare(
    targets: list[dict[str, Any]],
    produced: list[Path],
    kbe_dir: Path,
    *,
    phash_threshold: int = DEFAULT_PHASH_THRESHOLD,
) -> list[ComparisonResult]:
    """For every reproduction target, find the best produced artifact and compare.

    Returns one ComparisonResult per target. Targets with no match get
    ``status="no_artifact_produced"``; targets with no reference file get
    ``status="no_reference"`` — both are reproducibility findings.
    """
    results: list[ComparisonResult] = []

    for target in targets:
        tid = target.get("id", "?")
        kind = target.get("kind", "numerical_result")

        # Resolve the reference from KBE extraction.
        reference = resolve_reference(target, kbe_dir)
        if reference is None:
            results.append(ComparisonResult(
                artifact=tid, kind=kind,
                status="no_reference", method="none",
                detail=(
                    "No reference artifact found in kbe/references/. "
                    "KBE may not have been able to extract this item from the PDF."
                ),
            ))
            continue

        # Find produced artifacts matching this target.
        matches = match_target_to_artifacts(target, produced)
        if not matches:
            results.append(ComparisonResult(
                artifact=tid, kind=kind,
                status="no_artifact_produced", method="none",
                detail=(
                    f"No produced file matched target '{target.get('label', tid)}'. "
                    f"Produced files of this kind: "
                    f"{[p.name for p in produced if classify_artifact(p) == kind]!r}"
                ),
            ))
            continue

        # Use the best match (highest heuristic score).
        best = matches[0]
        result = _compare_one(
            target, best, reference, phash_threshold=phash_threshold,
        )
        # Annotate with match metadata so Review can see provenance.
        result.metadata["matched_file"] = str(best)
        result.metadata["match_candidates"] = [str(p) for p in matches]
        result.artifact = tid  # use target ID for traceability
        results.append(result)

    return results
