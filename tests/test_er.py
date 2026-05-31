"""Tests for the ER stage runner (tools/orchestrator/er.py).

ER is deferred in v0: it writes only the reserved skipped stub. These check the
contract the gate and Review depend on (er/er_output.json with status=skipped)
plus the workflow.log line, with no model or PDF backend involved.
"""

from __future__ import annotations

import json

from tools.orchestrator.er import run_er


def _er(root, title):
    return json.loads((root / "ai4r" / title / "er" / "er_output.json").read_text())


def test_writes_skipped_stub(tmp_path):
    out = run_er("a-paper", root=tmp_path)
    assert out["status"] == "skipped"
    assert out["paper_id"] == "a-paper"
    on_disk = _er(tmp_path, "a-paper")
    assert on_disk["status"] == "skipped"
    assert on_disk["paper_id"] == "a-paper"


def test_validator_required_key_present(tmp_path):
    # validate_review.sh requires only a `status` key on er/er_output.json.
    run_er("p", root=tmp_path)
    assert "status" in _er(tmp_path, "p")


def test_log_line_written(tmp_path):
    run_er("p", root=tmp_path)
    log = (tmp_path / "ai4r" / "p" / "logs" / "workflow.log").read_text()
    assert "ER status=skipped" in log


def test_idempotent_overwrite(tmp_path):
    run_er("p", root=tmp_path)
    first = _er(tmp_path, "p")
    run_er("p", root=tmp_path)  # second run must not raise or corrupt the file
    second = _er(tmp_path, "p")
    assert first["status"] == second["status"] == "skipped"
