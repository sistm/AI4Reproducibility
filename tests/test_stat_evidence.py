"""Tests for the call-site evidence extractor (tools/orchestrator/stat_evidence.py)."""

from __future__ import annotations

from tools.orchestrator.stat_evidence import PATTERNS, gather_stat_evidence


def _write(assets, name, text):
    (assets).mkdir(parents=True, exist_ok=True)
    (assets / name).write_text(text)


def test_finds_relevant_calls_and_includes_context(tmp_path):
    assets = tmp_path / "assets"
    _write(
        assets,
        "analysis.R",
        "library(stats)\n"
        "x <- rnorm(50)\n"
        "res <- t.test(x, mu = 0)\n"
        "print(res)\n",
    )
    ev = gather_stat_evidence(assets, window=1)
    ta = ev["cqv-stat-test-assumptions"]
    assert "t.test(" in ta
    assert "analysis.R:" in ta  # labelled with file
    assert "rnorm(50)" in ta  # window context line above the hit included


def test_irrelevant_code_yields_empty_evidence(tmp_path):
    assets = tmp_path / "assets"
    _write(assets, "util.R", "set.seed(1)\nmessage('hello')\n")
    ev = gather_stat_evidence(assets)
    assert all(v == "" for v in ev.values())


def test_python_signatures_detected(tmp_path):
    assets = tmp_path / "assets"
    _write(
        assets,
        "model.py",
        "from sklearn.model_selection import train_test_split\n"
        "X_tr, X_te = train_test_split(X)\n"
        "scaler.fit_transform(X)\n",
    )
    ev = gather_stat_evidence(assets)
    assert "train_test_split" in ev["cqv-stat-no-data-leakage"]


def test_every_check_has_a_key(tmp_path):
    assets = tmp_path / "assets"
    _write(assets, "a.R", "1\n")
    ev = gather_stat_evidence(assets)
    assert set(ev) == set(PATTERNS)


def test_bounded_by_max_chars(tmp_path):
    assets = tmp_path / "assets"
    _write(assets, "many.R", "\n".join("t.test(x)" for _ in range(2000)))
    ev = gather_stat_evidence(assets, max_chars=500)
    assert len(ev["cqv-stat-test-assumptions"]) <= 600  # cap + one final block tolerance


def test_non_source_and_unreadable_files_skipped(tmp_path):
    assets = tmp_path / "assets"
    _write(assets, "data.csv", "t.test,should,not,match\n")  # not a source suffix
    (assets / "binary.py").write_bytes(b"\xff\xfe t.test(\x00")  # decodes with replace
    ev = gather_stat_evidence(assets)
    assert "data.csv" not in ev["cqv-stat-test-assumptions"]
    # does not raise on the binary file; may or may not match after replacement
