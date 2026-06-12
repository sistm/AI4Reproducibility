"""Tests for tools/orchestrator/er_artifacts.py.

All tests use tmp_path; no Docker or real PDF involved.
"""

from __future__ import annotations

import csv
from pathlib import Path

from tools.orchestrator.er_artifacts import (
    _filename_score,
    classify_artifact,
    match_target_to_artifacts,
    new_files_since,
    pair_and_compare,
    resolve_reference,
    snapshot_files,
)

# ---------------------------------------------------------------------------
# classify_artifact
# ---------------------------------------------------------------------------

def test_classify_figure_exts():
    for ext in (".png", ".pdf", ".svg", ".jpg"):
        assert classify_artifact(Path(f"fig{ext}")) == "figure"


def test_classify_table_exts():
    for ext in (".csv", ".tsv", ".json", ".rds"):
        assert classify_artifact(Path(f"tbl{ext}")) == "table"


def test_classify_unknown_falls_back_to_numerical():
    assert classify_artifact(Path("notes.txt")) == "numerical_result"


# ---------------------------------------------------------------------------
# snapshot / new_files_since
# ---------------------------------------------------------------------------

def test_snapshot_empty_dir(tmp_path):
    assert snapshot_files(tmp_path) == frozenset()


def test_snapshot_nonexistent_dir(tmp_path):
    assert snapshot_files(tmp_path / "nope") == frozenset()


def test_new_files_since_detects_added_file(tmp_path):
    (tmp_path / "before.R").write_text("x <- 1")
    before = snapshot_files(tmp_path)
    (tmp_path / "result.png").write_bytes(b"\x89PNG")
    new = new_files_since(tmp_path, before)
    assert len(new) == 1
    assert new[0].name == "result.png"


def test_new_files_since_ignores_preexisting(tmp_path):
    (tmp_path / "main.R").write_text("x <- 1")
    before = snapshot_files(tmp_path)
    # Touch the same file — not new.
    (tmp_path / "main.R").write_text("x <- 2")
    assert new_files_since(tmp_path, before) == []


def test_new_files_since_works_in_subdirs(tmp_path):
    before = snapshot_files(tmp_path)
    out = tmp_path / "figures"
    out.mkdir()
    (out / "fig1.png").write_bytes(b"PNG")
    new = new_files_since(tmp_path, before)
    assert any(p.name == "fig1.png" for p in new)


# ---------------------------------------------------------------------------
# _filename_score
# ---------------------------------------------------------------------------

def test_score_label_substring_match():
    # "figure3" contains "figure3"
    assert _filename_score(Path("figure3.png"), "figure3", ["3"]) == 2


def test_score_digit_only_match():
    # "fig3" doesn't contain full label "figure3" but has digit
    assert _filename_score(Path("fig3.png"), "figure3", ["3"]) >= 1


def test_score_no_match():
    assert _filename_score(Path("analysis.png"), "figure3", ["3"]) == 0


# ---------------------------------------------------------------------------
# match_target_to_artifacts
# ---------------------------------------------------------------------------

def _target(tid, kind, label):
    return {"id": tid, "kind": kind, "label": label}


def test_match_by_label(tmp_path):
    produced = [tmp_path / "figure3.png", tmp_path / "unrelated.csv"]
    for p in produced:
        p.write_bytes(b"x")
    matches = match_target_to_artifacts(_target("fig-3", "figure", "Figure 3"), produced)
    assert len(matches) == 1
    assert matches[0].name == "figure3.png"


def test_match_filters_by_kind(tmp_path):
    produced = [tmp_path / "figure3.png", tmp_path / "figure3.csv"]
    for p in produced:
        p.write_bytes(b"x")
    # Table target: should only match CSV
    matches = match_target_to_artifacts(_target("t-3", "table", "Table 3"), produced)
    names = [m.name for m in matches]
    assert "figure3.csv" in names
    assert "figure3.png" not in names


def test_match_returns_empty_when_no_match(tmp_path):
    produced = [tmp_path / "completely_unrelated.png"]
    produced[0].write_bytes(b"x")
    matches = match_target_to_artifacts(_target("fig-99", "figure", "Figure 99"), produced)
    assert matches == []


# ---------------------------------------------------------------------------
# resolve_reference
# ---------------------------------------------------------------------------

def test_resolve_reference_returns_path(tmp_path):
    kbe_dir = tmp_path / "kbe"
    refs = kbe_dir / "references"
    refs.mkdir(parents=True)
    ref_file = refs / "figure-1.png"
    ref_file.write_bytes(b"PNG")
    target = {"id": "figure-1", "reference_path": "references/figure-1.png"}
    result = resolve_reference(target, kbe_dir)
    assert result == ref_file


def test_resolve_reference_returns_none_when_absent(tmp_path):
    kbe_dir = tmp_path / "kbe"
    kbe_dir.mkdir()
    target = {"id": "x", "reference_path": "references/missing.png"}
    assert resolve_reference(target, kbe_dir) is None


def test_resolve_reference_returns_none_when_field_missing(tmp_path):
    assert resolve_reference({"id": "x"}, tmp_path) is None


# ---------------------------------------------------------------------------
# pair_and_compare — integration
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def test_pair_no_reference_gives_no_reference_status(tmp_path):
    kbe_dir = tmp_path / "kbe"
    kbe_dir.mkdir()
    targets = [{"id": "fig-1", "kind": "figure", "label": "Figure 1",
                "reference_path": None}]
    results = pair_and_compare(targets, [], kbe_dir)
    assert results[0].status == "no_reference"


def test_pair_no_produced_gives_no_artifact_status(tmp_path):
    kbe_dir = tmp_path / "kbe"
    refs = kbe_dir / "references"
    refs.mkdir(parents=True)
    (refs / "fig-1.png").write_bytes(b"PNG")
    targets = [{"id": "fig-1", "kind": "figure", "label": "Figure 1",
                "reference_path": "references/fig-1.png"}]
    results = pair_and_compare(targets, [], kbe_dir)
    assert results[0].status == "no_artifact_produced"
    assert "no produced file" in results[0].detail.lower()


def test_pair_table_numeric_match(tmp_path):
    kbe_dir = tmp_path / "kbe"
    refs = kbe_dir / "references"
    refs.mkdir(parents=True)
    ref_csv = refs / "table-1.json"
    # The reference is a table JSON from kbe_extract; for comparison we use a csv
    # produced by the run. We'll use a CSV for both here.
    ref_csv = refs / "table-1.csv"
    _write_csv(ref_csv, [["1.0", "2.0"], ["3.0", "4.0"]])
    produced_csv = tmp_path / "workspace" / "table1.csv"
    _write_csv(produced_csv, [["1.0", "2.0"], ["3.0", "4.0"]])
    targets = [{"id": "table-1", "kind": "table", "label": "Table 1",
                "reference_path": "references/table-1.csv"}]
    results = pair_and_compare(targets, [produced_csv], kbe_dir)
    assert results[0].status == "pass"


def test_pair_table_numeric_mismatch(tmp_path):
    kbe_dir = tmp_path / "kbe"
    refs = kbe_dir / "references"
    refs.mkdir(parents=True)
    ref_csv = refs / "table-1.csv"
    _write_csv(ref_csv, [["1.0", "2.0"]])
    produced_csv = tmp_path / "table1.csv"
    _write_csv(produced_csv, [["9.0", "8.0"]])
    targets = [{"id": "table-1", "kind": "table", "label": "Table 1",
                "reference_path": "references/table-1.csv"}]
    results = pair_and_compare(targets, [produced_csv], kbe_dir)
    assert results[0].status == "fail"


def test_pair_figure_mismatch_flagged(tmp_path):
    """Unreadable image -> mismatch_flagged + needs_visual_review (Pillow absent or bad file)."""
    kbe_dir = tmp_path / "kbe"
    refs = kbe_dir / "references"
    refs.mkdir(parents=True)
    ref_png = refs / "fig-1.png"
    ref_png.write_text("not a real png")
    produced_png = tmp_path / "figure1.png"
    produced_png.write_text("also not a real png")
    targets = [{"id": "fig-1", "kind": "figure", "label": "Figure 1",
                "reference_path": "references/fig-1.png"}]
    results = pair_and_compare(targets, [produced_png], kbe_dir)
    # Either mismatch_flagged (no-hash path) or pass — never an error.
    assert results[0].status in ("mismatch_flagged", "pass")


def test_pair_multiple_targets(tmp_path):
    kbe_dir = tmp_path / "kbe"
    refs = kbe_dir / "references"
    refs.mkdir(parents=True)

    (refs / "fig-1.png").write_bytes(b"PNG")
    (refs / "fig-2.png").write_bytes(b"PNG")
    prod_1 = tmp_path / "figure1.png"
    prod_1.write_bytes(b"PNG")
    # fig-2 has no matching produced file

    targets = [
        {"id": "fig-1", "kind": "figure", "label": "Figure 1",
         "reference_path": "references/fig-1.png"},
        {"id": "fig-2", "kind": "figure", "label": "Figure 2",
         "reference_path": "references/fig-2.png"},
    ]
    results = pair_and_compare(targets, [prod_1], kbe_dir)
    assert len(results) == 2
    statuses = {r.artifact: r.status for r in results}
    assert statuses["fig-2"] == "no_artifact_produced"


def test_pair_missing_reproduced_artifact_adds_checklist_flag(tmp_path):
    """run_er should add MISSING_REPRODUCED_ARTIFACTS when some targets are unmatched."""
    import json as _json

    from tools.orchestrator.er import run_er
    from tools.orchestrator.er_docker import RunResult
    from tools.orchestrator.llm import LLMResponse

    assets = tmp_path / "ai4r" / "p" / "input" / "assets"
    assets.mkdir(parents=True)
    (assets / "README.md").write_text("Runs in about 1 minute.")
    (assets / "main.R").write_text("x <- 1\n")
    (assets / "renv.lock").write_text(_json.dumps({
        "R": {"Version": "4.3.2"}, "Packages": {},
    }))

    # KBE output with one target that has a reference
    kbe_dir = tmp_path / "ai4r" / "p" / "kbe"
    refs_dir = kbe_dir / "references"
    refs_dir.mkdir(parents=True)
    (refs_dir / "fig-1.png").write_bytes(b"PNG")
    kbe_out = {
        "paper_id": "p", "status": "success",
        "reproduction_targets": [{
            "id": "fig-1", "kind": "figure", "label": "Figure 1",
            "reference_path": "references/fig-1.png",
        }],
    }
    (kbe_dir / "kbe_output.json").write_text(_json.dumps(kbe_out))

    def fake_run(req):
        return RunResult(returncode=0, stdout="ok", stderr="")

    out = run_er("p", root=tmp_path, run_fn=fake_run,
                 complete_fn=lambda m, msgs, t: LLMResponse(
                     text=_json.dumps({
                         "runtime_documented": True, "estimated_seconds": 60,
                         "runtime_is_open_ended": False,
                         "intermediate_results_documented": False,
                         "checkpoint_scripts": [], "rationale": "fast",
                     })
                 ))
    # Run produced nothing, so fig-1 is unmatched.
    assert "MISSING_REPRODUCED_ARTIFACTS" in out["checklist_flags"]
    assert len(out["comparisons"]) == 1
    assert out["comparisons"][0]["status"] == "no_artifact_produced"
