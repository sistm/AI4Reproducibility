"""Tests for tools/orchestrator/kbe_extract.py.

All tests build small synthetic PDFs with pymupdf rather than using fixture
files, so they remain self-contained and the PDF content is fully controlled.
pymupdf is a runtime dependency so no importorskip needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from tools.orchestrator.kbe_extract import (
    _table_to_text,
    extract_references,
)

# ---------------------------------------------------------------------------
# Helpers: build tiny test PDFs
# ---------------------------------------------------------------------------


def _make_pdf_with_text_page(path: Path, text_lines: list[str] = ("Hello world",)) -> None:
    """Single-page PDF with text only."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 100
    for line in text_lines:
        page.insert_text((50, y), line, fontsize=11)
        y += 18
    doc.save(str(path))
    doc.close()


def _make_pdf_with_image_page(path: Path) -> None:
    """Single-page PDF with one embedded raster image."""
    import io

    from PIL import Image

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    img = Image.new("RGB", (200, 150), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    page.insert_image(pymupdf.Rect(50, 100, 250, 250), stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def _make_pdf_with_table_page(path: Path) -> None:
    """Single-page PDF with a drawn grid table."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    # Horizontal lines
    for y in [100, 120, 140, 160]:
        page.draw_line((50, y), (350, y))
    # Vertical lines
    for x in [50, 150, 250, 350]:
        page.draw_line((x, 100), (x, 160))

    cells = [["Group", "Mean", "SD"], ["A", "3.4", "0.5"], ["B", "5.1", "0.8"]]
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            page.insert_text((55 + c * 100, 116 + r * 20), cell, fontsize=9)

    doc.save(str(path))
    doc.close()


def _target(tid: str, kind: str, page: int) -> dict:
    return {"id": tid, "kind": kind, "label": f"Label {tid}", "source_page": page,
            "caption": "cap", "what_it_shows": "shows", "priority": "primary"}


# ---------------------------------------------------------------------------
# Manifest and directory
# ---------------------------------------------------------------------------

def test_manifest_json_written(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    refs_dir = tmp_path / "refs"
    targets = [_target("num-1", "numerical_result", 1)]
    extract_references(pdf, targets, refs_dir)
    manifest_path = refs_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert "num-1" in manifest


def test_output_dir_created_if_absent(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    refs_dir = tmp_path / "does" / "not" / "exist"
    extract_references(pdf, [_target("x", "numerical_result", 1)], refs_dir)
    assert refs_dir.is_dir()


def test_missing_pdf_returns_failed_entries(tmp_path):
    manifest = extract_references(
        tmp_path / "nope.pdf",
        [_target("x", "figure", 1)],
        tmp_path / "refs",
    )
    assert manifest["x"]["status"] == "failed"


def test_empty_targets_returns_empty_manifest(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    manifest = extract_references(pdf, [], tmp_path / "refs")
    assert manifest == {}


# ---------------------------------------------------------------------------
# Page-number handling
# ---------------------------------------------------------------------------

def test_null_source_page_fails(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    target = {"id": "x", "kind": "figure", "label": "L", "source_page": None}
    m = extract_references(pdf, [target], tmp_path / "refs")
    assert m["x"]["status"] == "failed"


def test_out_of_range_page_fails(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)  # 1 page only
    m = extract_references(pdf, [_target("x", "figure", 99)], tmp_path / "refs")
    assert m["x"]["status"] == "failed"


def test_zero_page_fails(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    target = {"id": "x", "kind": "figure", "label": "L", "source_page": 0}
    m = extract_references(pdf, [target], tmp_path / "refs")
    assert m["x"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Numerical result extraction
# ---------------------------------------------------------------------------

def test_numerical_result_writes_text_file(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf, ["The p-value was 0.042", "n=120 participants"])
    m = extract_references(pdf, [_target("nr-1", "numerical_result", 1)], tmp_path / "refs")
    assert m["nr-1"]["status"] == "extracted"
    txt = Path(tmp_path / "refs" / m["nr-1"]["path"].split("/")[-1]).read_text()
    assert "0.042" in txt


def test_numerical_result_path_in_manifest(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    m = extract_references(pdf, [_target("nr-1", "numerical_result", 1)], tmp_path / "refs")
    assert m["nr-1"]["path"] is not None
    assert m["nr-1"]["source_page"] == 1


# ---------------------------------------------------------------------------
# Figure extraction
# ---------------------------------------------------------------------------

def test_figure_page_render_written(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf, ["Figure 1 caption"])
    m = extract_references(pdf, [_target("fig-1", "figure", 1)], tmp_path / "refs")
    assert m["fig-1"]["status"] == "extracted"
    page_path = tmp_path / "refs" / m["fig-1"]["page_path"].split("/")[-1]
    assert page_path.is_file()
    assert page_path.stat().st_size > 0


def test_figure_uses_page_render_when_no_embedded_image(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf, ["Figure 2 caption"])
    m = extract_references(pdf, [_target("fig-2", "figure", 1)], tmp_path / "refs")
    assert m["fig-2"]["used_page_render"] is True
    assert m["fig-2"]["best_embedded"] is None


def test_figure_extracts_embedded_image(tmp_path):
    pytest.importorskip("PIL")
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_image_page(pdf)
    m = extract_references(pdf, [_target("fig-3", "figure", 1)], tmp_path / "refs")
    assert m["fig-3"]["status"] == "extracted"
    assert m["fig-3"]["used_page_render"] is False
    best = m["fig-3"]["best_embedded"]
    assert best is not None
    assert best["width"] == 200 and best["height"] == 150


def test_figure_primary_path_is_embedded_when_available(tmp_path):
    pytest.importorskip("PIL")
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_image_page(pdf)
    m = extract_references(pdf, [_target("fig-4", "figure", 1)], tmp_path / "refs")
    # Primary path should differ from page_path when embedded image found.
    assert m["fig-4"]["path"] != m["fig-4"]["page_path"]


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

def test_table_extraction_finds_grid(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_table_page(pdf)
    m = extract_references(pdf, [_target("tbl-1", "table", 1)], tmp_path / "refs")
    assert m["tbl-1"]["status"] == "extracted"
    assert m["tbl-1"]["n_tables_on_page"] >= 1


def test_table_json_has_rows(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_table_page(pdf)
    m = extract_references(pdf, [_target("tbl-2", "table", 1)], tmp_path / "refs")
    json_file = tmp_path / "refs" / m["tbl-2"]["path"].split("/")[-1]
    data = json.loads(json_file.read_text())
    assert "rows" in data
    assert len(data["rows"]) >= 2  # header + at least one data row


def test_table_no_grid_falls_back_to_text(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf, ["Group | Mean", "A | 3.4"])
    m = extract_references(pdf, [_target("tbl-3", "table", 1)], tmp_path / "refs")
    # No drawn grid -> text_fallback
    assert m["tbl-3"]["status"] == "text_fallback"
    assert m["tbl-3"]["path"] is not None


# ---------------------------------------------------------------------------
# Multi-target
# ---------------------------------------------------------------------------

def test_multiple_targets_independent_failures(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf_with_text_page(pdf)
    targets = [
        _target("nr-1", "numerical_result", 1),
        _target("bad", "figure", 999),        # out of range
        _target("nr-2", "numerical_result", 1),
    ]
    m = extract_references(pdf, targets, tmp_path / "refs")
    assert m["nr-1"]["status"] == "extracted"
    assert m["bad"]["status"] == "failed"
    assert m["nr-2"]["status"] == "extracted"


# ---------------------------------------------------------------------------
# _table_to_text helper
# ---------------------------------------------------------------------------

def test_table_to_text_basic():
    rows = [["A", "B", "C"], ["1", "2", "3"]]
    out = _table_to_text(rows)
    assert "A | B | C" in out
    assert "1 | 2 | 3" in out


def test_table_to_text_handles_none_cells():
    rows = [["A", None, "C"]]
    out = _table_to_text(rows)
    assert "A |  | C" in out


# ---------------------------------------------------------------------------
# Integration with run_kbe: reference_path injected into targets
# ---------------------------------------------------------------------------

def test_run_kbe_injects_reference_path(tmp_path):
    """reference_path is set on each target after extraction."""
    from tools.orchestrator.kbe import run_kbe
    from tools.orchestrator.llm import LLMResponse

    pdf = tmp_path / "ai4r" / "my-paper" / "input" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    _make_pdf_with_text_page(pdf, ["Figure 3 shows performance."])

    target_obj = {
        "id": "figure-3", "kind": "figure", "label": "Figure 3",
        "caption": "Performance curves.", "what_it_shows": "AUC",
        "source_page": 1, "priority": "primary",
    }

    def backend(model, messages, tools):
        u = messages[-1]["content"]
        if '{"paper_title"' in u:
            return LLMResponse(text='{"paper_title": "A Paper"}')
        if '{"reproduction_targets"' in u:
            return LLMResponse(text=json.dumps({"reproduction_targets": [target_obj]}))
        for f in ("structured_knowledge", "identified_assumptions",
                  "statistical_methods", "data_generation_processes",
                  "reproducibility_gaps"):
            if f'{{"{f}"' in u:
                return LLMResponse(text=json.dumps({f: []}))
        return LLMResponse(text="{}")

    out = run_kbe(
        "my-paper", root=tmp_path, complete_fn=backend,
        extract_fn=lambda p: "A" * 600,  # bypass real PDF text extraction
    )

    # reference_path should be injected (extraction runs on the real PDF)
    targets = out.get("reproduction_targets", [])
    assert len(targets) == 1
    assert targets[0]["reference_path"] is not None
    # The referenced file should exist on disk.
    ref_file = tmp_path / "ai4r" / "my-paper" / "kbe" / targets[0]["reference_path"]
    assert ref_file.is_file()
