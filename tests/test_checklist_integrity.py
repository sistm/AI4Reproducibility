"""Tests for cross-file checklist integrity.

These exercise ``check_also_enforces``: the referential-integrity guard on the
``also_enforces:`` block of ``cqv_checklist.yaml``. The JSON Schema validates
the shape of each entry but cannot confirm an id resolves across files, so this
is where that contract is enforced.
"""

from __future__ import annotations

import copy
from pathlib import Path

from tools.checklist_render import check_also_enforces, load_yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CQV_YAML = REPO_ROOT / "cqv_checklist.yaml"
REPRO_YAML = REPO_ROOT / "checklist.yaml"


def _cqv_data() -> dict:
    return load_yaml(CQV_YAML)


# ---------------------------------------------------------------------------
# Regression guard on the real data
# ---------------------------------------------------------------------------

def test_real_also_enforces_resolves():
    """Every also_enforces id in the shipped CQV YAML resolves to a real item."""
    assert check_also_enforces(_cqv_data(), REPRO_YAML) == []


def test_checklist_yaml_has_no_also_enforces_noop():
    """The reproducibility YAML has no block, so the check is a no-op."""
    assert check_also_enforces(load_yaml(REPRO_YAML), REPRO_YAML) == []


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_dangling_id_is_caught():
    data = _cqv_data()
    data["also_enforces"].append({"id": "bj-99-does-not-exist", "note": "x"})
    errs = check_also_enforces(data, REPRO_YAML)
    assert any("does not resolve" in e and "bj-99-does-not-exist" in e for e in errs)


def test_duplicate_id_is_caught():
    data = _cqv_data()
    first = copy.deepcopy(data["also_enforces"][0])
    data["also_enforces"].append(first)
    errs = check_also_enforces(data, REPRO_YAML)
    assert any("duplicate id" in e for e in errs)


def test_locally_redeclared_id_is_caught():
    data = _cqv_data()
    reused = data["items"][0]["id"]
    data["also_enforces"].append({"id": reused, "note": "x"})
    errs = check_also_enforces(data, REPRO_YAML)
    assert any("also a local item id" in e and reused in e for e in errs)


def test_missing_repro_file_is_caught(tmp_path):
    data = _cqv_data()
    errs = check_also_enforces(data, tmp_path / "nonexistent.yaml")
    assert any("not found" in e for e in errs)


def test_block_absent_returns_empty():
    assert check_also_enforces({"items": []}) == []
