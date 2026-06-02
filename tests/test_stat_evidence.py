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


def test_capitalised_method_names_match(tmp_path):
    # Regression: patterns must be case-insensitive. Real MTP code capitalises
    # method names and uses them in variable names / comments (bimj.202400278).
    assets = tmp_path / "assets"
    _write(
        assets,
        "DoFiguresTables.R",
        "Delta.Bonf = rep(alpha / m , m)\n"
        "Delta.Holm = alpha / (m : 1)\n"
        "Delta.BH = alpha * (1 : m) / m  # Benjamini-Hochberg\n"
        "R.BY = sum( p.sort <= Delta.BY )  # Benjamini-Yekutieli\n",
    )
    mt = gather_stat_evidence(assets)["cqv-stat-multiple-testing"]
    assert mt, "capitalised MTP method names must be detected (case-insensitive)"
    assert "Benjamini" in mt


def test_hand_rolled_test_statistics_detected(tmp_path):
    # Regression: methods/biostat code often computes tests by hand (a custom
    # statistic fed through a CDF) rather than calling t.test/wilcox.test.
    assets = tmp_path / "assets"
    _write(
        assets,
        "p-valuesCompute.R",
        "x0 = read.table('data.csv', header = TRUE, sep = ',')\n"
        "w = x0[, 'W_FSTUWT']\n"
        "Rbar = weighted.mean(R_ik, w)\n"
        "pvalue.2tail = 2 * pt(-abs(T_N), df = df.w)  # Brunner-Munzel\n",
    )
    ev = gather_stat_evidence(assets)
    assert ev["cqv-stat-test-assumptions"], "hand-rolled pt()-based test must be detected"
    assert ev["cqv-stat-representative-sampling"], "survey-weight idioms must be detected"


# ---------------------------------------------------------------------------
# Evidence budget: large implementation blocks must reach the judge (0030)
# Regression for bimj.202400278: the MTP-correction block (Delta.Bonf/Holm/BH/BY)
# was dropped whole because it exceeded the remaining per-check budget, so the
# multiple-testing judge saw only comments and false-FAILed "no correction".
# ---------------------------------------------------------------------------

def test_oversized_block_is_truncated_not_dropped(tmp_path):
    assets = tmp_path / "assets"
    code = "\n".join(f"Delta.Bonf = alpha / m  # threshold line {i}" for i in range(100))
    _write(assets, "a.R", code + "\n")
    # one merged block far exceeds this tiny budget; old code dropped it -> ""
    ev = gather_stat_evidence(assets, max_chars=300)["cqv-stat-multiple-testing"]
    assert ev, "oversized block must be truncated, not dropped to empty"
    assert "Delta.Bonf" in ev
    assert "truncated" in ev


def test_default_budget_surfaces_large_implementation_block(tmp_path):
    assets = tmp_path / "assets"
    lines = ["# overview of multiple testing and FDR control"]   # small comment block
    lines += ["sep <- 0"] * 5                                     # non-matching gap
    lines += [f"Delta.Bonf_{i} = alpha / m  # bonferroni {i}" for i in range(150)]  # big code block
    _write(assets, "analysis.R", "\n".join(lines) + "\n")
    ev = gather_stat_evidence(assets)["cqv-stat-multiple-testing"]
    # at the old 4000 budget the comment block consumed the lead and the big code
    # block was dropped; at the raised budget the implementation is represented
    assert "Delta.Bonf_0" in ev
    assert "Delta.Bonf_149" in ev or "truncated" in ev


def test_sampling_rubric_covers_survey_weights_and_multiscript():
    from tools.orchestrator.stat_judges import STAT_CHECKS
    rubric = next(c.rubric for c in STAT_CHECKS if c.item_id == "cqv-stat-representative-sampling")
    assert "weighted" in rubric.lower()
    assert "svy" in rubric.lower() or "survey" in rubric.lower()
    assert "ALL scripts" in rubric or "all scripts" in rubric.lower()
    assert "NOT a convenience sample" in rubric or "not a convenience" in rubric.lower()
