"""Tests for the KBE stage runner (tools/orchestrator/kbe.py).

Runs with an injected fake completion backend and a dummy PDF file, so it needs
neither LiteLLM nor a real PDF parser nor network access — the CI conditions.
The real SKILL file is read as the system prompt (it ships in the repo).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.orchestrator.kbe import run_kbe
from tools.orchestrator.llm import LLMResponse

VALIDATOR_REQUIRED_KEYS = {"paper_id", "status"}  # from validate_review.sh


def _seed_pdf(root: Path, title: str) -> Path:
    """Create the input/paper.pdf the stage expects to find."""
    pdf = root / "ai4r" / title / "input" / "paper.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.5 dummy")
    return pdf


def _fake_returning(text: str):
    def backend(model, messages, tools):
        return LLMResponse(text=text)

    return backend


def _read_output(root: Path, title: str) -> dict:
    return json.loads((root / "ai4r" / title / "kbe" / "kbe_output.json").read_text())


def test_success_path_writes_valid_output(tmp_path):
    _seed_pdf(tmp_path, "my-paper")
    model_json = json.dumps(
        {
            "paper_title": "A Study of Things",
            "structured_knowledge": {"blocks": []},
            "identified_assumptions": ["normality"],
            "statistical_methods": ["t-test"],
            "data_generation_processes": [],
            "reproducibility_gaps": ["no set.seed"],
            "partial_data": None,
            "notes": "looks fine",
        }
    )
    out = run_kbe("my-paper", root=tmp_path, complete_fn=_fake_returning(model_json))

    assert out["status"] == "success"
    assert out["paper_id"] == "my-paper"
    assert out["paper_title"] == "A Study of Things"
    assert out["extraction_timestamp"]  # populated by the orchestrator
    # files exist and the JSON satisfies the validator's required keys
    on_disk = _read_output(tmp_path, "my-paper")
    assert VALIDATOR_REQUIRED_KEYS <= set(on_disk)
    assert (tmp_path / "ai4r" / "my-paper" / "kbe" / "notes.md").read_text() == "looks fine"


def test_paper_id_is_forced_to_review_title(tmp_path):
    _seed_pdf(tmp_path, "real-id")
    # model tries to set a different paper_id; orchestrator must override it
    model_json = json.dumps({"paper_id": "WRONG", "notes": "x"})
    out = run_kbe("real-id", root=tmp_path, complete_fn=_fake_returning(model_json))
    assert out["paper_id"] == "real-id"


def test_missing_fields_are_defaulted(tmp_path):
    _seed_pdf(tmp_path, "sparse")
    out = run_kbe("sparse", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "success"
    for field in (
        "identified_assumptions",
        "statistical_methods",
        "data_generation_processes",
        "reproducibility_gaps",
    ):
        assert out[field] == []
    assert out["paper_title"] is None


def test_json_fences_are_tolerated(tmp_path):
    _seed_pdf(tmp_path, "fenced")
    fenced = "```json\n" + json.dumps({"notes": "ok"}) + "\n```"
    out = run_kbe("fenced", root=tmp_path, complete_fn=_fake_returning(fenced))
    assert out["status"] == "success"


def test_missing_pdf_is_a_failure_not_a_crash(tmp_path):
    # no _seed_pdf -> no input/paper.pdf
    (tmp_path / "ai4r" / "no-pdf").mkdir(parents=True)
    out = run_kbe("no-pdf", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "pdf_not_found"
    # output files still written
    assert _read_output(tmp_path, "no-pdf")["status"] == "failed"
    assert (tmp_path / "ai4r" / "no-pdf" / "kbe" / "notes.md").is_file()


def test_unparseable_model_output_is_partial_not_crash(tmp_path):
    _seed_pdf(tmp_path, "garbled")
    out = run_kbe("garbled", root=tmp_path, complete_fn=_fake_returning("not json at all"))
    assert out["status"] == "partial"
    assert out["failure_mode"] == "parse_error"
    on_disk = _read_output(tmp_path, "garbled")
    assert VALIDATOR_REQUIRED_KEYS <= set(on_disk)


def test_non_kebab_title_is_rejected(tmp_path):
    out = run_kbe("Not Kebab", root=tmp_path, complete_fn=_fake_returning("{}"))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "bad_review_title"


def test_backend_exception_is_caught(tmp_path):
    _seed_pdf(tmp_path, "boom")

    def exploding(model, messages, tools):
        raise RuntimeError("model exploded")

    out = run_kbe("boom", root=tmp_path, complete_fn=exploding)
    assert out["status"] == "partial"
    assert "model exploded" in out["failure_reason"]


def test_log_line_is_appended(tmp_path):
    _seed_pdf(tmp_path, "logged")
    run_kbe("logged", root=tmp_path, complete_fn=_fake_returning("{}"))
    log = (tmp_path / "ai4r" / "logged" / "logs" / "workflow.log").read_text()
    assert "KBE status=success" in log
