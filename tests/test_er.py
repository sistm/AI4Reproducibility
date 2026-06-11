"""Tests for the ER stage runner (tools/orchestrator/er.py).

Covers the v0 skipped stub (unchanged contract) plus the enabled execution
path: README pre-flight + Docker seam (Docker faked via run_fn), with no real
container or model involved.
"""

from __future__ import annotations

import json

from tools.orchestrator.er import run_er
from tools.orchestrator.er_docker import RunResult
from tools.orchestrator.llm import LLMResponse


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


# ---------------------------------------------------------------------------
# Enabled ER path (pre-flight + Docker seam) — Docker is faked
# ---------------------------------------------------------------------------


def _seed_assets(root, title, *, readme=None, renv=None, main=True):
    base = root / "ai4r" / title / "input" / "assets"
    base.mkdir(parents=True, exist_ok=True)
    if main:
        (base / "main.R").write_text("x <- 1\n")
    if readme is not None:
        (base / "README.md").write_text(readme)
    if renv is not None:
        (base / "renv.lock").write_text(renv)
    return base


_RENV = json.dumps({
    "R": {"Version": "4.3.2"},
    "Packages": {"ggplot2": {"Version": "3.5.0"}},
})


def _preflight_backend(payload: dict):
    def backend(model, messages, tools):
        return LLMResponse(text=json.dumps(payload))
    return backend


def test_enabled_no_readme_skips(tmp_path):
    _seed_assets(tmp_path, "p", renv=_RENV)
    out = run_er("p", root=tmp_path, enabled=True, complete_fn=_preflight_backend({}))
    assert out["status"] == "skipped_no_readme"
    assert "MISSING_README" in out["checklist_flags"]


def test_enabled_no_runtime_docs_skips_major(tmp_path):
    _seed_assets(tmp_path, "p", readme="Run main.R", renv=_RENV)
    out = run_er("p", root=tmp_path, enabled=True,
                 complete_fn=_preflight_backend({"runtime_documented": False}))
    assert out["status"] == "skipped_no_runtime_docs"
    assert "MISSING_RUNTIME_DOCS" in out["checklist_flags"]


def test_enabled_no_lockfile_skips_no_data(tmp_path):
    _seed_assets(tmp_path, "p", readme="Takes 2 min")
    out = run_er("p", root=tmp_path, enabled=True,
                 complete_fn=_preflight_backend({
                     "runtime_documented": True, "estimated_seconds": 120,
                 }))
    assert out["status"] == "skipped_no_data"


def test_enabled_full_run_success(tmp_path):
    _seed_assets(tmp_path, "p", readme="Takes 2 min", renv=_RENV)

    def fake_run(req):
        return RunResult(returncode=0, stdout="ok", stderr="")

    out = run_er("p", root=tmp_path, run_fn=fake_run,
                 complete_fn=_preflight_backend({
                     "runtime_documented": True, "estimated_seconds": 120,
                 }))
    assert out["status"] == "success"
    assert out["execution_mode"] == "full_run"
    assert out["image"].endswith(":r4.3.2")


def test_enabled_restore_failure(tmp_path):
    _seed_assets(tmp_path, "p", readme="Takes 2 min", renv=_RENV)

    def fake_run(req):
        # restore step fails
        return RunResult(returncode=1, stdout="", stderr="cannot restore")

    out = run_er("p", root=tmp_path, run_fn=fake_run,
                 complete_fn=_preflight_backend({
                     "runtime_documented": True, "estimated_seconds": 120,
                 }))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "renv_restore_failed"


def test_enabled_execution_timeout(tmp_path):
    _seed_assets(tmp_path, "p", readme="Takes 2 min", renv=_RENV)
    seq = [
        RunResult(returncode=0, stdout="restored", stderr=""),         # restore ok
        RunResult(returncode=124, stdout="", stderr="", timed_out=True),  # run times out
    ]
    calls = []

    def fake_run(req):
        calls.append(req)
        return seq[len(calls) - 1]

    out = run_er("p", root=tmp_path, run_fn=fake_run,
                 complete_fn=_preflight_backend({
                     "runtime_documented": True, "estimated_seconds": 120,
                 }))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "execution_timeout"


def test_default_still_skipped_stub(tmp_path):
    # Without enabled / run_fn, behaviour is the v0 skipped stub.
    out = run_er("p", root=tmp_path)
    assert out["status"] == "skipped"
    assert out["execution_mode"] == "skipped"


def test_output_has_status_key_on_every_path(tmp_path):
    # validator only requires `status`; assert it survives the enabled path.
    _seed_assets(tmp_path, "p", readme="Run main.R", renv=_RENV)
    run_er("p", root=tmp_path, enabled=True,
           complete_fn=_preflight_backend({"runtime_documented": False}))
    on_disk = _er(tmp_path, "p")
    assert "status" in on_disk
