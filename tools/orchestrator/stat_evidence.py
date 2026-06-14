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
_MIN_BLOCK_CHARS = 200  # don't bother appending a truncated sliver smaller than this

# Evidence budget (chars) by check severity.  Critical checks get the full
# budget; suggestion-level checks rarely need large windows.
_SEVERITY_BUDGETS: dict[str, int] = {
    "critical":   8_000,
    "major":      6_000,
    "minor":      4_000,
    "suggestion": 3_000,
}
_DEFAULT_BUDGET = 8_000


def _build_item_budgets() -> dict[str, int]:
    """Derive per-item char budget from STAT_CHECKS at import time."""
    try:
        from tools.orchestrator.stat_judges import STAT_CHECKS
        return {
            c.item_id: _SEVERITY_BUDGETS.get(c.severity, _DEFAULT_BUDGET)
            for c in STAT_CHECKS
        }
    except Exception:  # pragma: no cover
        return {}


_ITEM_BUDGETS: dict[str, int] = _build_item_budgets()


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
    # ── Data-handling patterns ────────────────────────────────────────────────
    "cqv-data-na-handling": _patterns(
        # NA guards used correctly
        r"\bna\.rm\s*=", r"\bna\.omit\s*\(", r"\bcomplete\.cases\s*\(",
        r"\bna\.action\s*=", r"\bna\.pass\b", r"\bna\.fail\b",
        r"drop_na\s*\(", r"\.dropna\s*\(", r"\.fillna\s*\(", r"\.isna\s*\(",
        r"pd\.isna\s*\(", r"pd\.notna\s*\(", r"np\.isnan\s*\(",
        # Aggregation functions that need na.rm
        r"\bsum\s*\(", r"\bmean\s*\(", r"\bvar\s*\(", r"\bsd\s*\(",
        r"\bmin\s*\(", r"\bmax\s*\(", r"\bmedian\s*\(",
        r"\bcolSums\s*\(", r"\bcolMeans\s*\(", r"\browSums\s*\(", r"\browMeans\s*\(",
        # NA detection
        r"\bis\.na\s*\(", r"\banyNA\s*\(", r"\bwhich\s*\(\s*is\.na",
    ),
    "cqv-data-explicit-types": _patterns(
        # Data loading — presence of type specification
        r"\bcolClasses\s*=", r"\bcol_types\s*=", r"\bdtype\s*=",
        # Explicit coercions
        r"\bas\.numeric\s*\(", r"\bas\.integer\s*\(", r"\bas\.character\s*\(",
        r"\bas\.factor\s*\(", r"\bas\.logical\s*\(", r"\bas\.double\s*\(",
        r"pd\.to_numeric\s*\(", r"pd\.to_datetime\s*\(", r"\.astype\s*\(",
        # Data reading (to check if types are specified)
        r"\bread\.csv\s*\(", r"\bread_csv\s*\(", r"\bread\.table\s*\(",
        r"\bfread\s*\(", r"\bread_excel\s*\(", r"\bpd\.read_csv\s*\(",
        # Type inspection
        r"\bclass\s*\(", r"\btypeof\s*\(", r"\bstr\s*\(", r"\bsapply\s*\(.*class",
    ),
    "cqv-data-no-unexpected-mutation": _patterns(
        # Superassignment (mutates outer/global state from inside a function)
        r"\s<<-\s",
        # data.table in-place assignment
        r":=\s", r"\bset\s*\(", r"\bsetnames\s*\(", r"\bsetcolorder\s*\(",
        # Python in-place
        r"\.drop\s*\(.*inplace\s*=\s*True",
        r"\.rename\s*\(.*inplace\s*=\s*True",
        r"\.fillna\s*\(.*inplace\s*=\s*True",
        r"\.dropna\s*\(.*inplace\s*=\s*True",
        # Function definitions that take df-like args
        r"function\s*\(.*data", r"function\s*\(.*df",
        r"def\s+\w+\s*\(.*df", r"def\s+\w+\s*\(.*data",
    ),
    # ── Performance patterns ──────────────────────────────────────────────────
    "cqv-perf-no-redundant-copies": _patterns(
        # Explicit copies
        r"\bcopy\s*\(", r"\.copy\s*\(\s*\)",
        # Identity-like assignment patterns
        r"\bdata\s*<-\s*data\b", r"\bdf\s*<-\s*df\b",
        # Full dataset copy before modification
        r"\w+\s*<-\s*\w+\s*\n.*\$",
        r"\w+_copy\b", r"\w+_bak\b", r"\w+_backup\b",
        # Repeated concatenation in loops (already caught by growing_vectors but
        # object_copying judge focuses on data-frame level)
        r"\brbind\s*\(", r"\bcbind\s*\(", r"\bbind_rows\s*\(",
    ),
    # ── Security patterns ─────────────────────────────────────────────────────
    "cqv-sec-path-sanitization": _patterns(
        # External input sources
        r"\bcommandArgs\s*\(", r"\breadline\s*\(", r"\bSys\.getenv\s*\(",
        r"\bargparse\b", r"\bsys\.argv\b", r"\boptparse\b",
        # Path construction
        r"\bfile\.path\s*\(", r"\bpaste\s*\(.*path", r"\bpaste0\s*\(.*path",
        r"\bnormalizePath\s*\(", r"\brealpath\b", r"\bpathlib\b",
        r"os\.path\.join\s*\(", r"os\.path\.abspath\s*\(",
        # Traversal indicators
        r"\.\./", r"\.\.\\\\",
        # Validation patterns
        r"stopifnot.*path", r"grepl.*\.\.", r"str_detect.*\.\.",
    ),
    # ── Documentation patterns ────────────────────────────────────────────────
    "cqv-doc-docstring-format": _patterns(
        # R roxygen
        r"^#'\s*@param\b", r"^#'\s*@return\b", r"^#'\s*@export\b",
        r"^#'\s*@examples\b", r"^#'\s*@description\b",
        r"^#'",  # any roxygen line (to surface presence of docs)
        # Python docstrings
        r'"""', r"'''",
        r"\bArgs\s*:\s*$", r"\bReturns\s*:\s*$", r"\bRaises\s*:\s*$",
        r"\bParameters\s*\n\s*-{3,}", r"\bReturns\s*\n\s*-{3,}",
        # Decorator-based docs
        r"@staticmethod", r"@classmethod", r"@property",
    ),
    # ── Testing patterns ──────────────────────────────────────────────────────
    "cqv-test-edge-cases": _patterns(
        # R testthat
        r"\btest_that\s*\(", r"\bexpect_equal\s*\(", r"\bexpect_error\s*\(",
        r"\bexpect_true\s*\(", r"\bexpect_false\s*\(", r"\bexpect_warning\s*\(",
        r"\bexpect_match\s*\(", r"\bexpect_null\s*\(",
        # Python pytest
        r"\bpytest\b", r"\bdef test_\w", r"\bassert\b",
        r"pytest\.raises\s*\(", r"pytest\.warns\s*\(",
        # Edge-case inputs
        r"\bNA\b", r"\bNaN\b", r"\bNULL\b", r"\bInf\b",
        r"integer\s*\(\s*0\s*\)", r"character\s*\(\s*0\s*\)",
        r"numeric\s*\(\s*0\s*\)", r"logical\s*\(\s*0\s*\)",
        r"pd\.DataFrame\s*\(\s*\)", r"np\.array\s*\(\s*\[\s*\]\s*\)",
        r'"edge"', r'"boundary"', r'"empty"', r'"zero"', r'"missing"',
    ),
    "cqv-test-integration": _patterns(
        # Test framework presence
        r"\btest_that\s*\(", r"\bdef test_\w", r"\bpytest\b",
        # Fixture data loading inside tests
        r"\bread\.csv\s*\(", r"\bread_csv\s*\(", r"\bfread\s*\(",
        r"pd\.read_csv\s*\(", r"\bread\.rds\s*\(", r"\breadRDS\s*\(",
        # Calling main entry points from tests
        r"\bsource\s*\(", r"\brun_analysis\b", r"\bmain\s*\(",
        r"\bimport\s+\w+\s*$", r"\bfrom\s+\w+\s+import\b",
        # Integration test markers / descriptions
        r"integration", r"end.?to.?end", r"e2e", r"pipeline",
        r"full.?run", r"full.?pipeline",
    ),
    # ── Dependencies patterns ─────────────────────────────────────────────────
    "cqv-dep-no-deprecated": _patterns(
        # All library/require calls — the judge decides which are deprecated
        r"\blibrary\s*\(", r"\brequire\s*\(",
        # Specific deprecated R packages
        r"\blibrary\s*\(\s*sp\b", r"\blibrary\s*\(\s*rgeos\b",
        r"\blibrary\s*\(\s*rgdal\b", r"\blibrary\s*\(\s*maptools\b",
        r"\blibrary\s*\(\s*plyr\b", r"\blibrary\s*\(\s*reshape2?\b",
        r"\blibrary\s*\(\s*xlsx\b", r"\blibrary\s*\(\s*RMySQL\b",
        # Python deprecated
        r"\bimport\s+distutils\b", r"\bfrom\s+distutils\b",
        r"\bimport\s+imp\b", r"\bfrom\s+imp\b",
        r"\bimport\s+nose\b", r"\bfrom\s+nose\b",
        # All imports (so the judge can survey the full dependency list)
        r"^import\s+\w+", r"^from\s+\w+\s+import\b",
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
    assets_dir: Path, *, window: int = 3, max_chars: int = _DEFAULT_BUDGET
) -> dict[str, str]:
    """Return ``{item_id: code-evidence}`` for each statistical-validity check.

    Evidence is matching call-sites plus ``window`` lines of context, labelled
    ``# <relpath>:<start>-<end>``. Capped per check by ``_ITEM_BUDGETS``
    (derived from check severity: critical 8 000, major 6 000, minor 4 000,
    suggestion 3 000 chars); ``max_chars`` is the fallback for any item not in
    the budget map. An oversized block is truncated (not dropped) so a large
    implementation block cannot lose the budget to small comment/header snippets.
    A check with no matches gets ``""`` (=> not_applicable downstream). Never raises.
    """
    files = [(p, _read_lines(p)) for p in _iter_source_files(assets_dir)]
    evidence: dict[str, str] = {}

    for item_id, patterns in PATTERNS.items():
        cap = _ITEM_BUDGETS.get(item_id, max_chars)
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
                if total + len(block) > cap:
                    # Truncate rather than drop: a large implementation block is
                    # usually the most relevant evidence and must not lose the
                    # budget to small comment/header snippets (bimj.202400278 --
                    # the MTP-correction block was dropped whole, which starved
                    # the multiple-testing judge into a false "no correction").
                    remaining = cap - total
                    if remaining >= _MIN_BLOCK_CHARS:
                        blocks.append(block[:remaining].rstrip() + "\n# ... (truncated)")
                    total = cap
                    break
                blocks.append(block)
                total += len(block) + 2
            if total >= cap:
                break
        evidence[item_id] = "\n\n".join(blocks)

    return evidence
