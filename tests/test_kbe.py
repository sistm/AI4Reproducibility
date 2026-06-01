"""Tests for the sectioned KBE stage runner (tools/orchestrator/kbe.py).

Uses an injected ``extract_fn`` (so no real PDF / pdfminer needed) and a fake
completion backend that answers per knowledge category by detecting which field
the section prompt asks for. No LiteLLM, no network — the CI conditions.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.orchestrator.kbe import _ARRAY_FIELDS, run_kbe
from tools.orchestrator.llm import LLMResponse

VALIDATOR_REQUIRED_KEYS = {"paper_id", "status"}
LONG_TEXT = "This is a manuscript about survival analysis. " * 60  # > 500 chars


def _seed_pdf(root: Path, title: str) -> None:
    pdf = root / "ai4r" / title / "input" / "paper.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.5 dummy")


def _read_output(root: Path, title: str) -> dict:
    return json.loads((root / "ai4r" / title / "kbe" / "kbe_output.json").read_text())


def _section_backend(per_field: dict[str, str]):
    """Fake backend: pick the response whose field appears in the section prompt."""

    def backend(model, messages, tools):
        user = messages[-1]["content"]
        for field, payload in per_field.items():
            if f'"{field}"' in user:
                return LLMResponse(text=payload)
        return LLMResponse(text="{}")

    return backend


def _all_valid() -> dict[str, str]:
    per = {"paper_title": json.dumps({"paper_title": "A Study of Things"})}
    for f in _ARRAY_FIELDS:
        per[f] = json.dumps({f: [f"{f}-item"]})
    return per


def _run(tmp_path, title, per_field, **kw):
    _seed_pdf(tmp_path, title)
    kw.setdefault("extract_fn", lambda p: LONG_TEXT)
    return run_kbe(title, root=tmp_path, complete_fn=_section_backend(per_field), **kw)


def test_all_sections_succeed(tmp_path):
    out = _run(tmp_path, "my-paper", _all_valid())
    assert out["status"] == "success"
    assert out["paper_id"] == "my-paper"
    assert out["paper_title"] == "A Study of Things"
    assert out["partial_data"] is None
    for f in _ARRAY_FIELDS:
        assert out[f] == [f"{f}-item"]
    assert VALIDATOR_REQUIRED_KEYS <= set(_read_output(tmp_path, "my-paper"))


def test_one_bad_section_is_partial(tmp_path):
    per = _all_valid()
    per["statistical_methods"] = "this is not json"  # one category fails to parse
    out = _run(tmp_path, "partialish", per)
    assert out["status"] == "partial"
    assert out["failure_mode"] == "template_partial"
    assert out["partial_data"]["sections_failed"] == ["statistical_methods"]
    assert "statistical_methods" not in out["partial_data"]["sections_extracted"]
    # the other categories still came through
    assert out["identified_assumptions"] == ["identified_assumptions-item"]
    # the failed category defaults to an empty array, not missing
    assert out["statistical_methods"] == []


def test_all_sections_fail_to_parse_is_failed(tmp_path):
    per = {f: "nope" for f in (*_ARRAY_FIELDS, "paper_title")}
    out = _run(tmp_path, "garbled", per)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "parse_error"
    assert VALIDATOR_REQUIRED_KEYS <= set(_read_output(tmp_path, "garbled"))


def test_transport_failure_on_all_sections_is_failed(tmp_path):
    _seed_pdf(tmp_path, "boom")

    def exploding(model, messages, tools):
        raise RuntimeError("gateway down")

    out = run_kbe("boom", root=tmp_path, complete_fn=exploding, extract_fn=lambda p: LONG_TEXT)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "llm_request_failed"
    assert "gateway down" in out["failure_reason"]


def test_empty_section_is_not_a_failure(tmp_path):
    # valid JSON but empty arrays / null title -> success with empty content
    per = {"paper_title": json.dumps({"paper_title": None})}
    for f in _ARRAY_FIELDS:
        per[f] = json.dumps({f: []})
    out = _run(tmp_path, "empty-ok", per)
    assert out["status"] == "success"
    assert out["paper_title"] is None
    assert all(out[f] == [] for f in _ARRAY_FIELDS)


def test_fences_tolerated(tmp_path):
    per = {f: "```json\n" + json.dumps({f: []}) + "\n```" for f in _ARRAY_FIELDS}
    per["paper_title"] = "```json\n" + json.dumps({"paper_title": "T"}) + "\n```"
    out = _run(tmp_path, "fenced", per)
    assert out["status"] == "success"
    assert out["paper_title"] == "T"


def test_paper_id_always_the_title_regardless_of_model(tmp_path):
    per = _all_valid()
    per["paper_title"] = json.dumps({"paper_title": "X", "paper_id": "WRONG"})
    out = _run(tmp_path, "real-id", per)
    assert out["paper_id"] == "real-id"


def test_pdf_not_found_is_failure(tmp_path):
    (tmp_path / "ai4r" / "no-pdf").mkdir(parents=True)
    out = run_kbe("no-pdf", root=tmp_path, complete_fn=_section_backend({}),
                  extract_fn=lambda p: LONG_TEXT)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "pdf_not_found"


def test_unreadable_pdf_is_failure(tmp_path):
    _seed_pdf(tmp_path, "bad-pdf")

    def boom_extract(p):
        raise RuntimeError("pdfminer choked")

    out = run_kbe("bad-pdf", root=tmp_path, complete_fn=_section_backend({}),
                  extract_fn=boom_extract)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "pdf_unreadable"


def test_text_too_short_is_failure(tmp_path):
    out = _run(tmp_path, "tiny", _all_valid(), extract_fn=lambda p: "too short")
    assert out["status"] == "failed"
    assert out["failure_mode"] == "text_too_short"


def test_non_kebab_title_rejected(tmp_path):
    out = run_kbe("Not Kebab", root=tmp_path, complete_fn=_section_backend({}),
                  extract_fn=lambda p: LONG_TEXT)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "bad_review_title"


def test_log_and_notes_written(tmp_path):
    _run(tmp_path, "logged", _all_valid())
    log = (tmp_path / "ai4r" / "logged" / "logs" / "workflow.log").read_text()
    assert "KBE status=success" in log
    assert (tmp_path / "ai4r" / "logged" / "kbe" / "notes.md").is_file()


def test_default_extract_chains_string_returning_tools(monkeypatch):
    """Regression: the registered pdf2text/clean_pdf_text return STRINGS (and
    raise on failure), not dicts. _default_extract must chain them as such."""
    import tools.tools as tools_mod
    from tools.orchestrator.kbe import _default_extract

    calls: list[tuple[str, dict]] = []

    def fake_run_tool(name, **kwargs):
        calls.append((name, kwargs))
        if name == "pdf2text":
            return "RAW from " + kwargs["pdf_path"]
        if name == "clean_pdf_text":
            return "CLEANED:" + kwargs["raw_text"]
        raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr(tools_mod, "run_tool", fake_run_tool)
    out = _default_extract(Path("/x/paper.pdf"))

    assert out == "CLEANED:RAW from /x/paper.pdf"
    assert [name for name, _ in calls] == ["pdf2text", "clean_pdf_text"]


def test_default_extract_propagates_tool_failure(monkeypatch):
    """A tool that raises (the wrappers' failure behaviour) must propagate."""
    import tools.tools as tools_mod
    from tools.orchestrator.kbe import _default_extract

    def boom(name, **kwargs):
        raise RuntimeError("pdf2text failed: encrypted")

    monkeypatch.setattr(tools_mod, "run_tool", boom)
    try:
        _default_extract(Path("/x/paper.pdf"))
    except RuntimeError as exc:
        assert "encrypted" in str(exc)
    else:
        raise AssertionError("expected RuntimeError to propagate")


def _truncating_backend(truncated_field, partial_text, valid):
    def backend(model, messages, tools):
        user = messages[-1]["content"]
        if f'"{truncated_field}"' in user:
            return LLMResponse(text=partial_text, finish_reason="length")
        for field, payload in valid.items():
            if f'"{field}"' in user:
                return LLMResponse(text=payload)
        return LLMResponse(text="{}")
    return backend


def test_truncated_section_salvages_prefix_and_marks_partial(tmp_path):
    _seed_pdf(tmp_path, "trunc")
    partial = '{"structured_knowledge": [{"k": "one"}, {"k": "two"}, {"k": "thr'
    out = run_kbe("trunc", root=tmp_path,
                  complete_fn=_truncating_backend("structured_knowledge", partial, _all_valid()),
                  extract_fn=lambda p: LONG_TEXT)
    assert out["status"] == "partial"
    assert out["structured_knowledge"] == [{"k": "one"}, {"k": "two"}]
    assert "output_truncated" in out["failure_reason"]
    assert "structured_knowledge" in out["partial_data"]["sections_failed"]
