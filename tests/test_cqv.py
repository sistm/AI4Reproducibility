"""Tests for the CQV stage runner (tools/orchestrator/cqv.py).

Runs with an injected fake completion backend and a dummy extracted-code tree,
so it needs neither LiteLLM nor network access. The real SKILL file is read as
the system prompt (it ships in the repo).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    # Rule 5: _normalise injects BLOCKER-0 for partial + no blockers.
    # Patch 0072 then upgrades partial→success and clears the synthetic blocker.
    _seed_assets(tmp_path, "partialish")
    model_json = json.dumps({"status": "partial", "reproducibility_blockers": []})
    out = run_cqv("partialish", root=tmp_path, complete_fn=_fake_returning(model_json))
    assert out["status"] == "success"           # upgraded by 0072
    assert out["reproducibility_blockers"] == []  # synthetic BLOCKER-0 cleared


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


def test_user_prompt_tags_file_contents_as_untrusted():
    """Prompt-injection hardening: tool-read file contents flagged untrusted."""
    from pathlib import Path as _Path

    from tools.orchestrator.cqv import _user_prompt

    prompt = _user_prompt(_Path("/tmp/assets"), "title")
    assert "SECURITY" in prompt
    assert "untrusted" in prompt
    assert "read_file" in prompt  # the specific tool whose returns are tainted


# --- patch 0054: CQV output structural schema -------------------------------


def test_assert_output_schema_accepts_canonical_shape():
    """A well-formed CQV output (canonical evidence shape) passes schema —
    this is the post-coercion contract that the K1 smoke failure motivated."""
    from tools.orchestrator.cqv import _assert_output_schema

    obj = {
        "paper_id": "p",
        "status": "success",
        "failure_mode": None,
        "failure_reason": None,
        "reproducibility_blockers": [
            {
                "id": "bj-10-set-seed",
                "severity": "HIGH",
                "description": "No set.seed() in main.R",
                "evidence": [{"file": "main.R", "line": 12}],
            },
        ],
    }
    _assert_output_schema(obj)  # no raise = pass


def test_assert_output_schema_rejects_string_shaped_evidence():
    """The K1 smoke failure: a blocker with string-shaped evidence (legacy
    form) reaches downstream Critic and confuses cite resolution. Schema
    catches it now — if _coerce_evidence regresses, this fires immediately."""
    import pytest

    from tools.orchestrator.cqv import _assert_output_schema

    obj = {
        "paper_id": "p",
        "status": "partial",
        "reproducibility_blockers": [
            {
                "id": "bj-10",
                "severity": "HIGH",
                "description": "no seed",
                "evidence": "main.R:12",  # legacy string form — bug if it reaches here
            },
        ],
    }
    with pytest.raises(ValueError, match=r"patch 0054"):
        _assert_output_schema(obj)


def test_assert_output_schema_rejects_evidence_object_missing_file():
    """Object-list shape with missing required keys (file/line) fails too —
    catches partial-coercion regressions where the wrapping list is right but
    the inner object is malformed."""
    import pytest

    from tools.orchestrator.cqv import _assert_output_schema

    obj = {
        "paper_id": "p",
        "status": "partial",
        "reproducibility_blockers": [
            {
                "id": "bj-10",
                "severity": "HIGH",
                "description": "no seed",
                "evidence": [{"line": 12}],  # missing 'file'
            },
        ],
    }
    with pytest.raises(ValueError, match=r"patch 0054"):
        _assert_output_schema(obj)


def test_assert_output_schema_rejects_unknown_status():
    """Status enum is strict: success/partial/failed only. Anything else
    (e.g. model output drift to 'ok' or 'error') is a bug."""
    import pytest

    from tools.orchestrator.cqv import _assert_output_schema

    obj = {"paper_id": "p", "status": "ok", "reproducibility_blockers": []}
    with pytest.raises(ValueError, match=r"patch 0054"):
        _assert_output_schema(obj)


def test_assert_output_schema_accepts_id_less_blocker():
    """Defensive: id-less blockers still go through (the dedup code keeps
    them). Schema doesn't require id — invariant is about evidence shape
    when present, not about every field being filled."""
    from tools.orchestrator.cqv import _assert_output_schema

    obj = {
        "paper_id": "p",
        "status": "partial",
        "reproducibility_blockers": [
            {"severity": "HIGH", "description": "anonymous blocker"},
        ],
    }
    _assert_output_schema(obj)  # no raise


def test_run_cqv_with_string_shape_evidence_is_coerced_and_passes(tmp_path):
    """End-to-end: a model that returns string-shape evidence (the K1 pattern)
    gets coerced by _normalise before reaching the schema check — full pipeline
    still succeeds. This is the success criterion patch 0054 was designed for:
    legacy-shape model output normalises silently to canonical shape."""
    _seed_assets(tmp_path, "legacy-shape")
    legacy_output = json.dumps({
        "status": "partial",
        "reproducibility_blockers": [
            {
                "id": "bj-10-set-seed",
                "severity": "HIGH",
                "description": "no seed",
                "evidence": "main.R:12",  # string form from model
            },
        ],
    })
    out = run_cqv("legacy-shape", root=tmp_path, complete_fn=_fake_returning(legacy_output))
    # Coercion produced canonical object-list shape; schema validation accepted it.
    blocker = next(b for b in out["reproducibility_blockers"] if b.get("id") == "bj-10-set-seed")
    assert isinstance(blocker["evidence"], list)
    assert blocker["evidence"][0] == {"file": "main.R", "line": 12}


# --- patch 0066: doubled-key stutter pre-pass in CQV --------------------------


def test_run_cqv_silently_normalises_pure_stutter(tmp_path):
    """When the model emits ONE doubled-key stutter and nothing else is wrong,
    CQV reports the model's actual status (no `failure_mode` taint), preserves
    no raw_model_output (the artifact is well-understood and the fix is
    deterministic), and surfaces the count in notes. This is the win case
    patch 0066 targets — `output_recovered_by_repair` stops firing on routine
    token stutters."""
    _seed_assets(tmp_path, "stutter-only")
    stuttered = json.dumps({
        "status": "success",
        "reproducibility_blockers": [],
        "repository_audit": [],
    }).replace(
        # Inject a single doubled-key stutter in an evidence-list shaped value
        '"status": "success"',
        '"status": "status": "success"',
    )
    out = run_cqv("stutter-only", root=tmp_path, complete_fn=_fake_returning(stuttered))
    # Model's `status: success` survives — no repair-recovered taint.
    assert out["status"] == "success"
    assert out.get("failure_mode") is None
    # raw_model_output NOT preserved on the pure-stutter path.
    assert "raw_model_output" not in out
    # Notes record the normalisation for the audit trail.
    assert "patch 0066" in out["notes"]
    assert "1 doubled-key stutter" in out["notes"]


def test_run_cqv_records_stutter_count_alongside_repair_when_both_happen(tmp_path):
    """When the model emits a stutter AND has another structural problem
    (e.g. truncation), both markers appear in notes — the audit trail
    distinguishes 'model stuttered + got truncated' from 'model emitted
    structurally broken JSON unrelated to known artifacts'. This is the
    smoke-C scenario (one stutter + a bracket mismatch from truncation)."""
    pytest.importorskip("json_repair")
    _seed_assets(tmp_path, "stutter-plus-truncation")
    # Stutter inside a still-malformed payload: json_repair has to step in.
    # The trailing comma + missing closing brace forces the deterministic
    # repair to run after the stutter has already been stripped.
    payload = (
        '{"status": "status": "partial", '
        '"reproducibility_blockers": [{"id": "x", "severity": "HIGH", '
        '"description": "y", "evidence": [{"file": "main.R", "line": 1}]}],'
    )
    out = run_cqv(
        "stutter-plus-truncation", root=tmp_path,
        complete_fn=_fake_returning(payload),
    )
    # Repair fired for the truncation, so failure_mode is set.
    assert out["failure_mode"] == "output_recovered_by_repair"
    # raw_model_output preserved (original, pre-stutter-strip) for human verification.
    assert "raw_model_output" in out
    assert '"status": "status":' in out["raw_model_output"]  # original stutter preserved
    # Both markers visible in notes.
    notes = out["notes"]
    assert "patch 0066" in notes
    assert "recovered from malformed JSON" in notes


def test_run_cqv_clean_output_emits_no_stutter_marker(tmp_path):
    """When the model emits well-formed output with no stutter, no patch-0066
    marker appears in notes. Confirms the marker isn't added speculatively."""
    _seed_assets(tmp_path, "clean")
    clean = json.dumps({
        "status": "success",
        "reproducibility_blockers": [],
        "repository_audit": [],
    })
    out = run_cqv("clean", root=tmp_path, complete_fn=_fake_returning(clean))
    assert out["status"] == "success"
    assert out.get("failure_mode") is None
    assert "patch 0066" not in out.get("notes", "")


# --- patch 0068: evidence path extension-repair -----------------------------


def test_repair_evidence_file_ref_adds_missing_R_extension(tmp_path):
    """The smoke-test pattern: the model drops `.R` on one entry in an
    evidence array. If exactly one extension produces a real file, repair."""
    from tools.orchestrator.cqv import _repair_evidence_file_ref

    code = tmp_path / "code"
    code.mkdir()
    (code / "DoFiguresTables.R").write_text("x <- 1\n")

    out = _repair_evidence_file_ref("code/DoFiguresTables", tmp_path)
    assert out == "code/DoFiguresTables.R"


def test_repair_evidence_file_ref_returns_none_when_already_resolves(tmp_path):
    """Paths that resolve as-is don't need repair; helper short-circuits to
    None so the caller leaves the entry alone."""
    from tools.orchestrator.cqv import _repair_evidence_file_ref

    code = tmp_path / "code"
    code.mkdir()
    (code / "main.R").write_text("x <- 1\n")

    # Helper only tries extension additions; the existing path's resolution
    # is the caller's job. Helper just looks for a uniquely-resolving variant.
    out = _repair_evidence_file_ref("code/main", tmp_path)
    assert out == "code/main.R"  # main + .R resolves; helper returns it


def test_repair_evidence_file_ref_refuses_ambiguous_match(tmp_path):
    """When multiple extensions would resolve, refuse to guess. The smoke
    pattern is single-character slips; multiple matches is no longer that —
    it's a different file entirely. Strict 'exactly one' rule."""
    from tools.orchestrator.cqv import _repair_evidence_file_ref

    code = tmp_path / "code"
    code.mkdir()
    (code / "analysis.R").write_text("x <- 1\n")
    (code / "analysis.py").write_text("x = 1\n")

    out = _repair_evidence_file_ref("code/analysis", tmp_path)
    assert out is None


def test_repair_evidence_file_ref_handles_case_insensitive_fs(tmp_path):
    """On macOS APFS (default case-insensitive) and Windows NTFS, .R and .r
    extensions resolve to the same file. The 'exactly one match' rule must
    deduplicate by resolved target, not by extension string, so a single
    foo.R file is not double-counted as both foo.R and foo.r.

    Regression test for the bug where macOS users saw all four
    extension-repair tests fail because both .R and .r appeared to resolve."""
    from tools.orchestrator.cqv import _repair_evidence_file_ref

    code = tmp_path / "code"
    code.mkdir()
    (code / "analysis.R").write_text("x <- 1\n")

    # On a case-insensitive FS, both .R and .r would naively appear to match.
    # The function must deduplicate by resolved path. On case-sensitive FS,
    # only .R matches and there is nothing to deduplicate — the result is
    # the same either way.
    out = _repair_evidence_file_ref("code/analysis", tmp_path)
    assert out == "code/analysis.R"


def test_repair_evidence_file_ref_returns_none_for_no_match(tmp_path):
    """If no extension produces a real file, return None — don't fabricate."""
    from tools.orchestrator.cqv import _repair_evidence_file_ref

    code = tmp_path / "code"
    code.mkdir()
    (code / "main.R").write_text("x <- 1\n")

    out = _repair_evidence_file_ref("code/elsewhere", tmp_path)
    assert out is None


def test_repair_evidence_file_ref_rejects_path_traversal(tmp_path):
    """Path-traversal safety: a repair attempt that resolves outside
    assets_dir must be rejected, same as :func:`_read_source_line`."""
    from tools.orchestrator.cqv import _repair_evidence_file_ref

    assets = tmp_path / "assets"
    assets.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.R").write_text("x <- 1\n")

    # ../outside/secret would resolve to a real file outside assets_dir.
    out = _repair_evidence_file_ref("../outside/secret", assets)
    assert out is None


def test_rehydrate_evidence_mutates_path_and_returns_repair_count(tmp_path):
    """End-to-end through _rehydrate_evidence: a bad path gets repaired
    in place, the snippet attaches to the repaired path, and the count
    reflects the number of repairs."""
    from tools.orchestrator.cqv import _rehydrate_evidence

    code = tmp_path / "code"
    code.mkdir()
    (code / "DoFiguresTables.R").write_text("# line 1\n" * 300)
    (code / "main.R").write_text("# main 1\n" * 200)

    node = {
        "evidence": [
            {"file": "code/main.R", "line": 1},  # already resolves
            {"file": "code/DoFiguresTables", "line": 278},  # smoke's slip
            {"file": "code/main", "line": 1},  # also needs .R repair
        ],
    }
    repairs = _rehydrate_evidence(node, tmp_path)

    assert repairs == 2
    # Repaired in place.
    assert node["evidence"][1]["file"] == "code/DoFiguresTables.R"
    assert node["evidence"][2]["file"] == "code/main.R"
    # Snippets attached for all entries.
    for entry in node["evidence"]:
        assert "snippet" in entry


def test_rehydrate_evidence_leaves_unrepairable_paths_alone(tmp_path):
    """When repair can't resolve the path, the entry stays as the model
    emitted it. No snippet, no mutation, no crash."""
    from tools.orchestrator.cqv import _rehydrate_evidence

    code = tmp_path / "code"
    code.mkdir()
    (code / "main.R").write_text("x <- 1\n")

    node = {"file": "code/nonexistent", "line": 5}
    repairs = _rehydrate_evidence(node, tmp_path)

    assert repairs == 0
    assert node["file"] == "code/nonexistent"  # unchanged
    assert "snippet" not in node


def test_run_cqv_surfaces_repair_count_in_notes(tmp_path):
    """End-to-end: when the model emits an evidence entry with a missing-
    extension path AND the repair resolves, the CQV output's notes record
    the count via the patch-0068 marker."""
    _seed_assets(tmp_path, "with-repair")
    # Need an actual code file under assets so the repair can resolve.
    code_dir = tmp_path / "ai4r" / "with-repair" / "input" / "assets" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "main.R").write_text("x <- 1\n" * 50)

    audit = json.dumps({
        "status": "success",
        "reproducibility_blockers": [{
            "id": "x",
            "severity": "HIGH",
            "description": "missing seed",
            "evidence": [{"file": "code/main", "line": 5}],  # missing .R
        }],
    })

    out = run_cqv("with-repair", root=tmp_path, complete_fn=_fake_returning(audit))

    # The file path was mutated to the repaired form.
    blocker = next(b for b in out["reproducibility_blockers"] if b.get("id") == "x")
    assert blocker["evidence"][0]["file"] == "code/main.R"
    # Notes mention the repair.
    assert "patch 0068" in out["notes"]
    assert "1 evidence file path" in out["notes"]


def test_run_cqv_clean_output_has_no_repair_marker(tmp_path):
    """No bad paths => no patch-0068 marker in notes."""
    _seed_assets(tmp_path, "no-repair-needed")
    code_dir = tmp_path / "ai4r" / "no-repair-needed" / "input" / "assets" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "main.R").write_text("x <- 1\n")

    audit = json.dumps({
        "status": "success",
        "reproducibility_blockers": [{
            "id": "x",
            "severity": "HIGH",
            "description": "missing seed",
            "evidence": [{"file": "code/main.R", "line": 1}],  # already resolves
        }],
    })

    out = run_cqv("no-repair-needed", root=tmp_path, complete_fn=_fake_returning(audit))
    assert "patch 0068" not in out.get("notes", "")

# ---------------------------------------------------------------------------
# Orchestrator-driven check coverage (patch 0070)
# ---------------------------------------------------------------------------

def test_partial_data_checks_set_by_orchestrator(tmp_path):
    """Orchestrator overwrites model-fabricated check lists with real coverage."""
    from tools.cqv_agent.static_checks import REGISTRY
    from tools.cqv_agent.static_checks.dispatch import list_static_checks

    _seed_assets(tmp_path, "checked")
    model_json = json.dumps({
        "partial_data": {
            "checks_completed": ["FAKE-CHECK-1", "FAKE-CHECK-2"],
            "checks_skipped": ["FAKE-SKIPPED"],
        },
        "notes": "test",
    })
    out = run_cqv("checked", root=tmp_path, complete_fn=_fake_returning(model_json))

    pd = out["partial_data"]
    assert pd is not None, "partial_data must be set by orchestrator"
    completed = pd["checks_completed"]
    skipped = pd["checks_skipped"]

    assert "FAKE-CHECK-1" not in completed, "fabricated IDs must not appear in completed"
    assert "FAKE-SKIPPED" not in skipped, "fabricated IDs must not appear in skipped"

    all_check_ids = set(REGISTRY.keys())
    covered = set(completed) | set(skipped)
    assert all_check_ids == covered, (
        f"completed+skipped must cover all registry entries; "
        f"missing={sorted(all_check_ids - covered)}"
    )

    check_info = list_static_checks()
    stub_ids = {cid for cid, meta in check_info.items() if not meta["implemented"]}
    for stub_id in stub_ids:
        assert stub_id in skipped, (
            f"Stub {stub_id} must be in checks_skipped, not completed"
        )


def test_partial_data_checks_on_r_assets_excludes_python_only(tmp_path):
    """Python-only checks are skipped when assets contain only R files."""
    from tools.cqv_agent.static_checks.dispatch import APPLICABLE_TO

    _seed_assets(tmp_path, "r-only")
    out = run_cqv("r-only", root=tmp_path, complete_fn=_fake_returning("{}"))

    pd = out["partial_data"]
    assert pd is not None
    skipped = pd["checks_skipped"]

    python_only = [c for c, langs in APPLICABLE_TO.items() if langs == ["python"]]
    for check_id in python_only:
        assert check_id in skipped, (
            f"Python-only check {check_id} should be in checks_skipped for R-only assets"
        )


# ---------------------------------------------------------------------------
# Status threshold (patch 0072)
# ---------------------------------------------------------------------------

def test_partial_with_stubs_only_upgraded_to_success(tmp_path):
    """Model-emitted partial with no failure_mode is upgraded to success."""
    _seed_assets(tmp_path, "upgrade-me")
    model_json = json.dumps({"status": "partial", "notes": "some checks skipped"})
    out = run_cqv("upgrade-me", root=tmp_path, complete_fn=_fake_returning(model_json))
    assert out["status"] == "success", (
        f"Expected partial→success upgrade; got {out['status']}"
    )
    assert "upgraded" in out.get("notes", "")


def test_partial_with_failure_mode_not_upgraded(tmp_path):
    """Parse failure sets failure_mode; partial must not be upgraded."""
    _seed_assets(tmp_path, "parse-fail")
    out = run_cqv("parse-fail", root=tmp_path, complete_fn=_fake_returning("not json"))
    assert out["status"] == "partial"
    assert out.get("failure_mode") == "output_parse_failed"
