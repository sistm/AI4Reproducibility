"""Tests for ER Docker seam (er_docker) and comparison (er_compare).

Docker is never invoked: a fake RunFn is injected. pHash tests use synthetic
in-memory images only when Pillow is available, and skip otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.orchestrator.er_compare import (
    ComparisonResult,
    compare_figure,
    compare_numeric,
)
from tools.orchestrator.er_docker import (
    RunRequest,
    RunResult,
    image_for_r_version,
    restore_and_run,
)

# ---- image_for_r_version ---------------------------------------------------

def test_image_tag_from_clean_version():
    assert image_for_r_version("4.3.2").endswith(":r4.3.2")


def test_image_tag_from_messy_version_string():
    assert image_for_r_version("R version 4.4.1 (2024-06-14)").endswith(":r4.4.1")


def test_image_tag_default_on_none():
    assert image_for_r_version(None).endswith(":r4.4.2")


# ---- restore_and_run seam --------------------------------------------------

def test_restore_failure_skips_run(tmp_path):
    calls = []

    def fake_run(req: RunRequest) -> RunResult:
        calls.append(req)
        # First call is restore — fail it.
        return RunResult(returncode=1, stdout="", stderr="restore boom")

    restore, run = restore_and_run(
        tmp_path, "img", ["Rscript", "main.R"], run_timeout=60, run_fn=fake_run,
    )
    assert not restore.ok
    assert run is None
    assert len(calls) == 1  # run was never attempted


def test_restore_success_then_run(tmp_path):
    seq = [
        RunResult(returncode=0, stdout="restored", stderr=""),   # restore
        RunResult(returncode=0, stdout="ran", stderr=""),        # run
    ]
    calls = []

    def fake_run(req: RunRequest) -> RunResult:
        calls.append(req)
        return seq[len(calls) - 1]

    restore, run = restore_and_run(
        tmp_path, "img", ["Rscript", "main.R"], run_timeout=60, run_fn=fake_run,
    )
    assert restore.ok and run is not None and run.ok
    # Restore call has network on, run call has network off.
    assert calls[0].network is True
    assert calls[1].network is False


def test_run_result_ok_property():
    assert RunResult(returncode=0, stdout="", stderr="").ok
    assert not RunResult(returncode=1, stdout="", stderr="").ok
    assert not RunResult(returncode=0, stdout="", stderr="", timed_out=True).ok


# ---- compare_numeric -------------------------------------------------------

def test_numeric_identical_passes():
    r = compare_numeric("T1", [[1.0, 2.0], [3.0, 4.0]], [[1.0, 2.0], [3.0, 4.0]])
    assert r.status == "pass"


def test_numeric_within_tolerance_passes():
    r = compare_numeric("T1", [[1.005]], [[1.0]], rtol=0.01)
    assert r.status == "pass"


def test_numeric_outside_tolerance_fails():
    r = compare_numeric("T1", [[1.5]], [[1.0]], rtol=0.01)
    assert r.status == "fail"
    assert r.metadata["cells_failed"] == 1


def test_numeric_shape_mismatch_fails():
    r = compare_numeric("T1", [[1.0, 2.0]], [[1.0]])
    assert r.status == "fail"
    assert "Shape mismatch" in r.detail


# ---- compare_figure (pHash gate + LLM escalation) --------------------------

def _make_image(path: Path, color: int) -> bool:
    """Write a solid-colour PNG; return False if Pillow is unavailable."""
    try:
        from PIL import Image
    except ImportError:
        return False
    Image.new("L", (64, 64), color).save(path)
    return True


def test_figure_identical_passes_via_phash(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    if not (_make_image(a, 128) and _make_image(b, 128)):
        pytest.skip("Pillow not available")
    r = compare_figure(a, b)
    assert r.status == "pass"
    assert r.method == "phash"


def test_figure_phash_unavailable_without_llm_is_mismatch_flagged(tmp_path):
    # Non-image files -> _phash returns None -> mismatch_flagged + needs_visual_review.
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_text("not an image")
    b.write_text("not an image")
    r = compare_figure(a, b)
    assert r.status == "mismatch_flagged"
    assert r.needs_visual_review is True


def test_figure_escalates_to_llm_when_phash_unavailable(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_text("not an image")
    b.write_text("not an image")

    def llm(repro, ref):
        return {"classification": "cosmetic", "detail": "axis labels differ only"}

    r = compare_figure(a, b, llm_compare_fn=llm)
    assert r.status == "pass"
    assert r.method == "phash+llm"


def test_figure_llm_substantive_fails(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_text("x")
    b.write_text("y")

    def llm(repro, ref):
        return {"classification": "substantive", "detail": "different trend direction"}

    r = compare_figure(a, b, llm_compare_fn=llm)
    assert r.status == "fail"


def test_comparison_result_to_dict_roundtrip():
    r = ComparisonResult(artifact="f.png", kind="figure", status="pass", method="phash")
    d = r.to_dict()
    assert d["artifact"] == "f.png" and d["status"] == "pass"
    assert d["needs_visual_review"] is False


def test_comparison_result_mismatch_flagged_sets_needs_visual_review():
    r = ComparisonResult(
        artifact="f.png", kind="figure",
        status="mismatch_flagged", method="phash",
        needs_visual_review=True,
    )
    assert r.to_dict()["needs_visual_review"] is True
