"""Tests for the CQV stage runner (tools/orchestrator/cqv.py).

Runs with an injected fake completion backend and a dummy extracted-code tree,
so it needs neither LiteLLM nor network access. The real SKILL file is read as
the system prompt (it ships in the repo).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.orchestrator.cqv import run_cqv
from tools.orchestrator.llm import LLMResponse

VALIDATOR_REQUIRED_KEYS = {"paper_id", "status"}  # from validate_review.sh


def _seed_assets(root: Path, title: str) -> Path:
    """Create input/assets/ with a code file, as preflight extraction would."""
    assets = root / "ai4r" / title / "input" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "analysis.R").write_text("set.seed(1)\n")
    return assets


def _fake_returning(text: str):
    def backend(model, messages, tools):
        return LLMResponse(text=text)

    return backend


def _read_output(root: Path, title: str) -> dict:
    return json.loads((root / "ai4r" / title / "cqv" / "cqv_output.json").read_text())


def test_success_path_writes_valid_output(tmp_path):
    _seed_assets(tmp_path, "my-paper")
    model_json = json.dumps(
        {
            "repository_audit": {"readme_present": True},
            "dependency_validation": {"lockfile": "renv.lock"},
            "execution_readiness": "ready",
            "reproducibility_blockers": [],
            "notes": "clean repo",
        }
    )
    out = run_cqv("my-paper", root=tmp_path, complete_fn=_fake_returning(model_json))

    assert out["status"] == "success"
    assert out["paper_id"] == "my-paper"
    assert out["audit_timestamp"]
    assert out["execution_readiness"] == "ready"
    on_disk = _read_output(tmp_path, "my-paper")
    assert VALIDATOR_REQUIRED_KEYS <= set(on_disk)
    assert (tmp_path / "ai4r" / "my-paper" / "cqv" / "repo_analysis.md").read_text() == "clean repo"


def test_paper_title_is_stripped(tmp_path):
    # CQV must not emit paper_title (context-boundary rule 3)
    _seed_assets(tmp_path, "no-title")
    model_json = json.dumps({"paper_title": "Should Not Be Here", "notes": "x"})
    out = run_cqv("no-title", root=tmp_path, complete_fn=_fake_returning(model_json))
    assert "paper_title" not in out
    assert "paper_title" not in _read_output(tmp_path, "no-title")


def test_paper_id_is_forced(tmp_path):
    _seed_assets(tmp_path, "real-id")
    out = run_cqv(
        "real-id", root=tmp_path, complete_fn=_fake_returning(json.dumps({"paper_id": "WRONG"}))
    )
    assert out["paper_id"] == "real-id"


def test_model_signalled_partial_gets_a_blocker(tmp_path):
    _seed_assets(tmp_path, "partialish")
    # model reports partial but forgets to add a blocker -> rule 5 injects one
    model_json = json.dumps({"status": "partial", "reproducibility_blockers": []})
    out = run_cqv("partialish", root=tmp_path, complete_fn=_fake_returning(model_json))
    assert out["status"] == "partial"
    assert len(out["reproducibility_blockers"]) >= 1


def test_defaults_filled(tmp_path):
    _seed_assets(tmp_path, "sparse")
    out = run_cqv("sparse", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "success"
    assert out["execution_readiness"] == "unknown"
    assert out["reproducibility_blockers"] == []
    assert out["repository_audit"] is None


def test_empty_assets_is_failure(tmp_path):
    # directory exists but contains no files
    (tmp_path / "ai4r" / "empty" / "input" / "assets").mkdir(parents=True)
    out = run_cqv("empty", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "assets_directory_empty"
    assert len(out["reproducibility_blockers"]) >= 1
    assert (tmp_path / "ai4r" / "empty" / "cqv" / "repo_analysis.md").is_file()


def test_missing_assets_dir_is_failure(tmp_path):
    (tmp_path / "ai4r" / "no-assets").mkdir(parents=True)
    out = run_cqv("no-assets", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "assets_directory_empty"


def test_unparseable_output_is_partial_with_blocker(tmp_path):
    _seed_assets(tmp_path, "garbled")
    out = run_cqv("garbled", root=tmp_path, complete_fn=_fake_returning("not json"))
    assert out["status"] == "partial"
    assert out["failure_mode"] == "output_parse_failed"
    assert len(out["reproducibility_blockers"]) >= 1
    assert VALIDATOR_REQUIRED_KEYS <= set(_read_output(tmp_path, "garbled"))


def test_non_kebab_title_rejected(tmp_path):
    out = run_cqv("Not Kebab", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "bad_review_title"


def test_backend_exception_is_failed_llm_request(tmp_path):
    _seed_assets(tmp_path, "boom")

    def exploding(model, messages, tools):
        raise RuntimeError("model exploded")

    out = run_cqv("boom", root=tmp_path, complete_fn=exploding)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "llm_request_failed"
    assert "model exploded" in out["failure_reason"]


def test_fences_tolerated_and_log_written(tmp_path):
    _seed_assets(tmp_path, "fenced")
    fenced = "```json\n" + json.dumps({"notes": "ok"}) + "\n```"
    run_cqv("fenced", root=tmp_path, complete_fn=_fake_returning(fenced))
    log = (tmp_path / "ai4r" / "fenced" / "logs" / "workflow.log").read_text()
    assert "CQV status=success" in log
