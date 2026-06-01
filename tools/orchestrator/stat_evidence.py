"""Call-site evidence extraction for the statistical-validity judges.

A statistical judge is only as good as what it sees, and the failure modes in
``references/STATISTICAL_VALIDATION.md`` are all concrete code signatures: a
``t.test`` with no preceding ``shapiro.test``, ``scale(df)`` before a split,
raw p-values with no ``p.adjust``. So evidence is the *actual call-sites*, not a
prose summary (decision: option (b) call-site extraction).

For each statistical-validity check, this scans the submission's R/Python source
for the relevant signatures and returns the matching lines plus a small window
of surrounding context, keyed by checklist ``item_id``. Empty evidence for a
check means "no relevant code found" — the judge then marks it not_applicable
without a model call (see :mod:`tools.orchestrator.stat_judges`).

Heuristic by nature: patterns aim to surface candidate call-sites for the LLM to
judge, not to decide anything themselves. Bounded per check (``max_chars``) so a
large repo cannot blow the token budget. Never raises — unreadable files are
skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

# Source files worth scanning. ``.R`` lowercases to ``.r``; ``.Rmd`` to ``.rmd``.
_SOURCE_SUFFIXES = {".r", ".py", ".rmd", ".qmd"}
_MAX_FILE_BYTES = 1_000_000  # skip files larger than this (data dumps, etc.)


def _patterns(*raw: str) -> list[re.Pattern[str]]:
    # Case-insensitive: method names and idioms appear capitalised in real code
    # (Bonferroni, Holm, BH) and in comments/variable names, not just lowercased.
    return [re.compile(p, re.IGNORECASE) for p in raw]


# item_id -> regexes that surface candidate call-sites for that check.
# R and Python signatures are mixed; the judge sorts out relevance. Patterns
# cover both library calls (t.test, p.adjust) AND hand-rolled statistics
# (custom test statistics fed through pt()/pnorm(); MTP thresholds computed
# directly), since methods and biostat code frequently implements tests by hand.
PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "cqv-stat-test-assumptions": _patterns(
        r"\bt\.test\s*\(", r"\bwilcox\.test\s*\(", r"\baov\s*\(", r"\banova\s*\(",
        r"\blm\s*\(", r"\bglm\s*\(", r"\blmer\s*\(",
        r"\bshapiro\.test\s*\(", r"\bqqnorm\s*\(", r"\bleveneTest\s*\(", r"\bbartlett\.test\s*\(",
        r"ttest_(ind|rel|1samp)", r"\bmannwhitneyu\s*\(", r"\bf_oneway\s*\(",
        r"\bshapiro\s*\(", r"\blevene\s*\(", r"\bnormaltest\s*\(",
        # hand-rolled tests: test statistic -> p-value via a CDF, or named tests
        r"\bpt\s*\(", r"\bpnorm\s*\(", r"\bpchisq\s*\(", r"\bpf\s*\(",
        r"brunner", r"munzel", r"kendall", r"wilcoxon", r"mann.?whitney",
        r"p[._-]?values?\b", r"test.?statistic",
    ),
    "cqv-stat-multiple-testing": _patterns(
        r"\bp\.adjust\s*\(", r"\bmultipletests\s*\(",
        # method names (any case) — appear in code, comments, and variable names
        r"bonferroni", r"\bholm\b", r"sidak", r"šid", r"benjamini", r"hochberg",
        r"yekutieli", r"\bfdr\b", r"\bfwer\b", r"\bmtp\b", r"\bBH\b", r"\bBY\b",
        r"multiple.?test", r"family.?wise", r"false.?discovery", r"\bdelta\.",
        # individual test calls (counting how many tests are run)
        r"\bt\.test\s*\(", r"\bwilcox\.test\s*\(", r"\bprop\.test\s*\(", r"\bchisq\.test\s*\(",
        r"\bfisher\.test\s*\(", r"\bcor\.test\s*\(",
        r"chi2_contingency", r"\bpearsonr\s*\(", r"\bspearmanr\s*\(",
    ),
    "cqv-stat-no-data-leakage": _patterns(
        r"\bscale\s*\(", r"\bpreProcess\s*\(", r"\bcreateDataPartition\s*\(", r"\banti_join\s*\(",
        r"\bmice\s*\(", r"\bsample_frac\s*\(",
        r"train_test_split", r"\bKFold\b", r"cross_val", r"\bfit_transform\s*\(",
        r"StandardScaler", r"SimpleImputer", r"\bPipeline\s*\(", r"\.fit_transform\b",
        r"train.?(set|data|index)", r"test.?(set|data|index)", r"\bimputation\b",
    ),
    "cqv-stat-ci-coverage": _patterns(
        r"\bconfint\s*\(", r"\bboot\s*\(", r"\bboot\.ci\s*\(", r"\bquantile\s*\(",
        r"\bconf_int\s*\(", r"\bbootstrap\s*\(", r"\bBCa\b", r"\.interval\s*\(",
        r"percentile", r"proportion_confint",
        # Bayesian interval idioms
        r"credible", r"\bHPD\b", r"\bHPDinterval\b", r"posterior.?(interval|quantile)",
    ),
    "cqv-stat-representative-sampling": _patterns(
        r"\bsample\s*\(", r"\bsample_frac\s*\(", r"\bsample_n\s*\(",
        r"\bread\.csv\s*\(", r"\bread_csv\s*\(", r"\bread\.table\s*\(", r"\bfread\s*\(",
        r"\bread_excel\s*\(", r"read_sav", r"\bsubset\s*\(", r"\bfilter\s*\(",
        r"exclu", r"inclusion", r"np\.random", r"\.sample\s*\(",
        # survey weighting (representativeness is usually handled via weights)
        r"weighted\.mean", r"\bcov\.wt\s*\(", r"svydesign", r"\bsvy", r"\bweights?\b",
        r"_WT\b", r"poststrat", r"\bstratif",
    ),
    "cqv-stat-no-post-hoc": _patterns(
        r"\blm\s*\(", r"\bglm\s*\(", r"\blmer\s*\(", r"\bformula\b",
        r"\bsubset\s*\(", r"\bfilter\s*\(", r"smf\.", r"\bols\s*\(",
        r"exclu", r"\bdrop\b", r"post.?hoc", r"sensitivity", r"specif",
    ),
    "cqv-stat-model-diagnostics": _patterns(
        r"\bresiduals\s*\(", r"\bqqnorm\s*\(", r"\bqqPlot\s*\(", r"\bncvTest\s*\(",
        r"\boutlierTest\s*\(", r"\bplot\s*\(\s*\w*mod", r"\binfluence\s*\(",
        r"calibration", r"\broc\b", r"confusionMatrix", r"roc_curve", r"calibration_curve",
        r"\.resid\b", r"plot_diagnostics",
        # MCMC convergence diagnostics for Bayesian models
        r"burn.?in", r"\bgibbs\b", r"\bmcmc\b", r"traceplot", r"geweke", r"gelman",
        r"\brhat\b", r"effectiveSize", r"n[._]eff", r"\bconverg",
    ),
}


def _iter_source_files(assets_dir: Path) -> list[Path]:
    out = []
    for p in sorted(assets_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        out.append(p)
    return out


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _merge_windows(hits: list[int], window: int, n_lines: int) -> list[tuple[int, int]]:
    """Merge hit line indices into [start, end) ranges padded by ``window``."""
    ranges: list[tuple[int, int]] = []
    for h in hits:
        start, end = max(0, h - window), min(n_lines, h + window + 1)
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def gather_stat_evidence(
    assets_dir: Path, *, window: int = 3, max_chars: int = 4000
) -> dict[str, str]:
    """Return ``{item_id: code-evidence}`` for each statistical-validity check.

    Evidence is matching call-sites plus ``window`` lines of context, labelled
    ``# <relpath>:<start>-<end>``. Capped at ``max_chars`` per check. A check
    with no matches gets ``""`` (⇒ not_applicable downstream). Never raises.
    """
    files = [(p, _read_lines(p)) for p in _iter_source_files(assets_dir)]
    evidence: dict[str, str] = {}

    for item_id, patterns in PATTERNS.items():
        blocks: list[str] = []
        total = 0
        for path, lines in files:
            hits = sorted(
                {i for i, line in enumerate(lines) for pat in patterns if pat.search(line)}
            )
            if not hits:
                continue
            try:
                label = path.relative_to(assets_dir).as_posix()
            except ValueError:
                label = path.name
            for start, end in _merge_windows(hits, window, len(lines)):
                body = "\n".join(f"{n + 1}: {lines[n]}" for n in range(start, end))
                block = f"# {label}:{start + 1}-{end}\n{body}"
                if total + len(block) > max_chars:
                    break
                blocks.append(block)
                total += len(block) + 2
            if total >= max_chars:
                break
        evidence[item_id] = "\n\n".join(blocks)

    return evidence
