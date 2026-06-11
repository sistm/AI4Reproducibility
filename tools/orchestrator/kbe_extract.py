"""KBE reference extraction: pull figure/table artifacts from the PDF (patch B).

KBE identifies *which* figures and tables to reproduce (via ``reproduction_targets``);
this module handles the mechanical extraction of the reference artifacts themselves.
Outputs land in ``kbe/references/`` alongside ``kbe_output.json``.

Extraction strategy by kind:

  figure          — render the target page at 2x scale to PNG (unambiguous and
                    always works). Also extract the largest embedded image on
                    that page as a secondary candidate if one exists. ER uses
                    the embedded image for pHash comparison when available
                    (cleaner signal than a full-page render).

  table           — locate tables on the target page via pymupdf's layout
                    analyser; serialise cell contents as JSON + a plain-text
                    grid for human inspection. If multiple tables appear on the
                    page, all are saved and the one with the most cells is
                    flagged as the primary match.

  numerical_result — save the text of the target page as plain UTF-8; the
                    specific number(s) are somewhere in that text and Review
                    can cite them from context.

All extraction is best-effort: a failure on one target never aborts the others.
Targets with ``source_page: null`` or out-of-range pages get
``reference_path: null`` in the manifest. ER checks the manifest before
attempting comparison.

The manifest (``kbe/references/manifest.json``) is the stable contract
consumed by ER.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# pymupdf is a runtime dependency (pyproject.toml) — no optional guard needed.
import pymupdf

_DPI_SCALE = 2.0   # renders at ~144 DPI — enough for pHash; tweak if needed
_MANIFEST_NAME = "manifest.json"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_references(
    pdf_path: Path,
    targets: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Extract reference artifacts for each reproduction target.

    Args:
        pdf_path:   Path to the manuscript PDF.
        targets:    The ``reproduction_targets`` list from kbe_output.json.
        output_dir: Where to write extracted files (created if absent).

    Returns:
        Manifest dict: ``{target_id: {kind, path, status, ...}}``.
        Always returns a dict, even on total failure; callers treat absent
        keys as extraction-failed for that target.
    """
    manifest: dict[str, dict[str, Any]] = {}

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as exc:
        return {t["id"]: _failed(t, f"could not open PDF: {exc}") for t in targets
                if isinstance(t, dict) and t.get("id")}

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        for target in targets:
            if not isinstance(target, dict):
                continue
            tid = target.get("id")
            if not tid:
                continue
            entry = _extract_one(doc, target, output_dir)
            manifest[tid] = entry
    finally:
        doc.close()

    # Write the manifest so ER can read it without re-parsing kbe_output.json.
    (output_dir / _MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


# ---------------------------------------------------------------------------
# Per-target dispatch
# ---------------------------------------------------------------------------


def _extract_one(
    doc: pymupdf.Document,
    target: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    kind = target.get("kind", "numerical_result")
    tid = target["id"]
    page_idx = _resolve_page(doc, target.get("source_page"))

    if page_idx is None:
        return _failed(target, "source_page missing or out of range")

    try:
        page = doc[page_idx]
        if kind == "figure":
            return _extract_figure(doc, page, tid, page_idx, output_dir)
        if kind == "table":
            return _extract_table(page, tid, page_idx, output_dir)
        return _extract_text(page, tid, page_idx, output_dir)
    except Exception as exc:
        return _failed(target, f"extraction error: {exc}")


# ---------------------------------------------------------------------------
# Figure extraction
# ---------------------------------------------------------------------------


def _extract_figure(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    tid: str,
    page_idx: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Render the full page and, separately, extract the largest embedded image."""

    # 1. Full-page render (always succeeds when the page is readable).
    page_png = output_dir / f"{tid}_page.png"
    mat = pymupdf.Matrix(_DPI_SCALE, _DPI_SCALE)
    pix = page.get_pixmap(matrix=mat)
    pix.save(str(page_png))

    # 2. Try to find the largest embedded image on this page. Many PDF figures
    #    are stored as embedded raster images; this gives a cleaner reference
    #    for pHash comparison than the full-page render.
    best_png: Path | None = None
    best_info: dict[str, Any] = {}
    best_area = 0
    candidates: list[dict[str, Any]] = []

    for img_idx, img_meta in enumerate(page.get_images(full=True)):
        xref = img_meta[0]
        try:
            img_pix = pymupdf.Pixmap(doc, xref)
            # Normalise CMYK → RGB so we can save as PNG cleanly.
            if img_pix.n - img_pix.alpha > 3:
                img_pix = pymupdf.Pixmap(pymupdf.csRGB, img_pix)
            area = img_pix.width * img_pix.height
            cand_path = output_dir / f"{tid}_candidate_{img_idx}.png"
            img_pix.save(str(cand_path))
            info = {
                "path": str(cand_path.relative_to(output_dir.parent)),
                "width": img_pix.width,
                "height": img_pix.height,
                "area": area,
            }
            candidates.append(info)
            if area > best_area:
                best_area = area
                best_png = cand_path
                best_info = info
        except Exception:
            continue

    # The primary reference for ER is the best embedded image when one exists
    # (cleaner pHash signal); fall back to the page render otherwise.
    primary = best_png or page_png
    primary_rel = str(primary.relative_to(output_dir.parent))

    return {
        "id": tid,
        "kind": "figure",
        "status": "extracted",
        "path": primary_rel,
        "page_path": str(page_png.relative_to(output_dir.parent)),
        "source_page": page_idx + 1,  # back to 1-based for human readability
        "embedded_candidates": candidates,
        "best_embedded": best_info if best_png else None,
        "used_page_render": best_png is None,
    }


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------


def _extract_table(
    page: pymupdf.Page,
    tid: str,
    page_idx: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Extract tables from the page; serialise to JSON + plain-text grid."""

    table_finder = page.find_tables()
    tables = table_finder.tables

    if not tables:
        # No structured table detected: fall back to page text so ER at least
        # has something to work with.
        txt_path = output_dir / f"{tid}_text.txt"
        txt_path.write_text(page.get_text("text"), encoding="utf-8")
        return {
            "id": tid,
            "kind": "table",
            "status": "text_fallback",
            "path": str(txt_path.relative_to(output_dir.parent)),
            "source_page": page_idx + 1,
            "note": "No structured table detected on page; saved page text instead.",
        }

    # Save all tables found on the page; the primary is the one with the most
    # cells (a rough proxy for "the main table").
    saved: list[dict[str, Any]] = []
    primary_path: Path | None = None
    primary_n_cells = -1

    for i, table in enumerate(tables):
        rows: list[list[str | None]] = table.extract()
        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=0)
        n_cells = n_rows * n_cols

        json_path = output_dir / f"{tid}_table_{i}.json"
        json_path.write_text(
            json.dumps({"rows": rows}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        txt_path = output_dir / f"{tid}_table_{i}.txt"
        txt_path.write_text(_table_to_text(rows), encoding="utf-8")

        entry: dict[str, Any] = {
            "path": str(json_path.relative_to(output_dir.parent)),
            "text_path": str(txt_path.relative_to(output_dir.parent)),
            "n_rows": n_rows,
            "n_cols": n_cols,
        }
        saved.append(entry)

        if n_cells > primary_n_cells:
            primary_n_cells = n_cells
            primary_path = json_path

    primary_rel = str(primary_path.relative_to(output_dir.parent))  # type: ignore[union-attr]
    return {
        "id": tid,
        "kind": "table",
        "status": "extracted",
        "path": primary_rel,
        "source_page": page_idx + 1,
        "n_tables_on_page": len(tables),
        "tables": saved,
    }


# ---------------------------------------------------------------------------
# Numerical result extraction
# ---------------------------------------------------------------------------


def _extract_text(
    page: pymupdf.Page,
    tid: str,
    page_idx: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Save the full page text; the specific number is somewhere in it."""
    txt_path = output_dir / f"{tid}.txt"
    txt_path.write_text(page.get_text("text"), encoding="utf-8")
    return {
        "id": tid,
        "kind": "numerical_result",
        "status": "extracted",
        "path": str(txt_path.relative_to(output_dir.parent)),
        "source_page": page_idx + 1,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_page(doc: pymupdf.Document, source_page: Any) -> int | None:
    """Convert a 1-based human page number to a 0-based pymupdf index.

    Returns None when ``source_page`` is unusable.
    """
    if not isinstance(source_page, int) or isinstance(source_page, bool):
        return None
    # KBE stores 1-based page numbers; pymupdf uses 0-based.
    idx = source_page - 1
    if idx < 0 or idx >= len(doc):
        return None
    return idx


def _failed(target: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "id": target.get("id"),
        "kind": target.get("kind"),
        "status": "failed",
        "path": None,
        "reason": reason,
    }


def _table_to_text(rows: list[list[str | None]]) -> str:
    """Render a list-of-lists table as a plain pipe-separated text grid."""
    lines: list[str] = []
    for row in rows:
        cells = [str(c) if c is not None else "" for c in row]
        lines.append(" | ".join(cells))
    return "\n".join(lines)
