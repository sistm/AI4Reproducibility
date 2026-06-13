"""
AST-based static checks for R using tree-sitter-languages (patches 0096-0098).

Requires the optional ``tree-sitter-languages`` package (with the matching
``tree-sitter==0.21.x`` ABI). When unavailable every check returns
``not_implemented`` so the rest of the pipeline is unaffected.

Checks
------
* check_undefined_references  -- identifiers used but not defined in the repo
  or base-R whitelist.
* check_function_signatures   -- call sites to locally-defined functions with
  unknown named arguments or too many positional arguments.
* check_dead_code             -- functions defined in the repo but never called
  anywhere (and not a likely entry-point name).
* check_loop_invariants       -- size-computation calls (length/nrow/ncol/dim)
  inside loops whose argument does not change in the loop body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._common import CheckResult, iter_source_files, read_text_safe, relpath

# ---------------------------------------------------------------------------
# Optional import -- graceful degradation when tree-sitter is absent
# ---------------------------------------------------------------------------

try:
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        from tree_sitter_languages import get_parser as _get_parser  # type: ignore[import]
    _PARSER = _get_parser("r")
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False
    _PARSER = None  # type: ignore[assignment]


def _not_impl() -> CheckResult:
    return CheckResult(
        tool_id="check_undefined_references",
        status="not_implemented",
        summary=(
            "AST checks require 'tree-sitter-languages' "
            "(pip install tree-sitter-languages 'tree-sitter==0.21.3'). "
            "Install it and re-run."
        ),
        evidence=[],
        metadata={"reason": "tree-sitter-languages not available"},
    )


def _not_impl_for(tool_id: str) -> CheckResult:
    r = _not_impl()
    return CheckResult(
        tool_id=tool_id,
        status="not_implemented",
        summary=r.summary,
        evidence=[],
        metadata=r.metadata,
    )


def _parse(source: bytes) -> Any:
    try:
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            return _PARSER.parse(source)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Base-R / common-package whitelist (check_undefined_references)
# ---------------------------------------------------------------------------

_WHITELIST: frozenset[str] = frozenset({
    # Constants
    "TRUE","FALSE","T","F","NULL","NA","Inf","NaN",
    "NA_integer_","NA_real_","NA_complex_","NA_character_",
    "LETTERS","letters","month.abb","month.name","pi",
    # Type constructors / coercions
    "c","list","vector","array","matrix",
    "numeric","integer","double","complex","character","logical","raw",
    "factor","ordered","data.frame","tibble","data.table",
    "as.numeric","as.integer","as.double","as.complex",
    "as.character","as.logical","as.factor","as.ordered",
    "as.data.frame","as.tibble","as.list","as.vector",
    "as.matrix","as.array","as.Date","as.POSIXct","as.POSIXlt",
    "as.environment","as.function","as.name","as.symbol",
    # Type tests
    "is.numeric","is.integer","is.double","is.complex",
    "is.character","is.logical","is.factor","is.ordered",
    "is.data.frame","is.list","is.vector","is.matrix","is.array",
    "is.null","is.na","is.nan","is.finite","is.infinite",
    "is.function","is.environment","is.primitive","is.recursive",
    "is.atomic","is.element",
    # Structure
    "length","lengths","nrow","ncol","dim","names","dimnames",
    "colnames","rownames","class","typeof","mode","storage.mode",
    "str","attributes","attr","structure",
    # Sequences
    "seq","seq_along","seq_len","seq.int","sequence",
    "rep","rep_len","rep.int",
    # Subsetting helpers
    "head","tail","rev","which","which.min","which.max",
    # Ordering
    "sort","order","rank","xtfrm",
    # Set ops
    "unique","duplicated","table","tabulate",
    "union","intersect","setdiff",
    # Aggregation
    "sum","prod","cumsum","cumprod","cummax","cummin",
    "min","max","pmin","pmax","range",
    "mean","median","var","sd","cov","cor",
    "weighted.mean","colSums","colMeans","rowSums","rowMeans",
    # Logical
    "any","all","xor",
    # Math
    "abs","sqrt","exp","log","log2","log10","log1p","expm1",
    "ceiling","floor","round","trunc","signif",
    "sin","cos","tan","asin","acos","atan","atan2",
    "sinh","cosh","tanh","asinh","acosh","atanh",
    "sign","choose","factorial","beta","gamma","lgamma","lbeta",
    "Arg","Mod","Re","Im","Conj","diff","append",
    # Matrix
    "t","solve","det","crossprod","tcrossprod","diag",
    "outer","kronecker","svd","qr","chol","eigen",
    "upper.tri","lower.tri","col","row",
    # String
    "paste","paste0","sprintf","format","formatC","prettyNum",
    "nchar","substr","substring","strsplit","chartr",
    "toupper","tolower","trimws","startsWith","endsWith",
    "strrep","grep","grepl","regexpr","gregexpr","regmatches",
    "sub","gsub",
    # I/O
    "cat","print","message","warning","stop","stopifnot",
    "readline","readLines","writeLines","scan",
    "read.csv","read.csv2","read.table","read.delim","read.fwf",
    "write.csv","write.csv2","write.table",
    "readRDS","saveRDS","load","save","source","sink",
    # File system
    "file.path","file.exists","file.create","file.copy","file.remove",
    "dir.create","dir.exists","list.files","list.dirs",
    "basename","dirname","normalizePath","path.expand",
    "tempfile","tempdir","getwd","setwd",
    # System
    "Sys.time","Sys.sleep","Sys.getenv","Sys.setenv","Sys.info",
    "proc.time","date","system.time","system","shell",
    # Functional
    "lapply","sapply","vapply","mapply","tapply","rapply",
    "apply","Map","Reduce","Filter","Find","Position",
    "do.call","Vectorize","match.fun",
    # Environment
    "environment","new.env","parent.env","globalenv",
    "baseenv","emptyenv","environmentName",
    "ls","objects","exists","get","assign","rm","remove",
    "parent.frame","sys.frame","sys.call","match.arg","match.call",
    "missing","sys.function","sys.nframe","on.exit","local",
    # Options / conditions
    "options","getOption",".Machine",".GlobalEnv",".Random.seed",
    "tryCatch","withCallingHandlers","try",
    "simpleError","simpleWarning","simpleMessage","simpleCondition",
    "conditionMessage","conditionCall",
    "withRestarts","invokeRestart",
    # OO
    "UseMethod","NextMethod","inherits","is",
    "setClass","setGeneric","setMethod","setRefClass",
    "new","initialize","show","validObject","R6Class",
    # Misc
    "identical","all.equal","isTRUE","isFALSE",
    "switch","invisible","nargs","Recall","force","numeric_version","package_version","getRversion","compareVersion",
    "require","library","loadNamespace","requireNamespace",
    "installed.packages","packageVersion",
    # stats
    "lm","glm","lmer","glmer","nlme","gam",
    "predict","fitted","residuals","hatvalues","cooks.distance",
    "anova","summary","coef","coefficients","confint",
    "vcov","sigma","deviance","logLik","AIC","BIC",
    "model.matrix","model.frame","terms","formula","update",
    "offset","contrasts","poly","ns","bs",
    "pnorm","qnorm","dnorm","rnorm",
    "pt","qt","dt","rt","pf","qf","df","rf",
    "pchisq","qchisq","dchisq","rchisq",
    "pbeta","qbeta","dbeta","rbeta",
    "pgamma","qgamma","dgamma","rgamma",
    "pexp","qexp","dexp","rexp",
    "pbinom","qbinom","dbinom","rbinom",
    "ppois","qpois","dpois","rpois",
    "punif","qunif","dunif","runif",
    "phyper","qhyper","dhyper","rhyper",
    "pnbinom","qnbinom","dnbinom","rnbinom",
    "pgeom","qgeom","dgeom","rgeom",
    "pweibull","qweibull","dweibull","rweibull",
    "pcauchy","qcauchy","dcauchy","rcauchy",
    "plogis","qlogis","dlogis","rlogis",
    "cor.test","t.test","chisq.test","fisher.test",
    "shapiro.test","ks.test","wilcox.test","kruskal.test",
    "var.test","bartlett.test","fligner.test",
    "aov","TukeyHSD","pairwise.t.test",
    "prop.test","binom.test","poisson.test",
    "acf","pacf","arima","Box.test",
    "quantile","IQR","mad","ecdf","density",
    "p.adjust",
    "kmeans","hclust","cutree","dist","cmdscale",
    "prcomp","princomp","factanal",
    "mahalanobis","cov2cor",
    "optim","optimize","uniroot","nlm","nlminb","constrOptim",
    "integrate",
    "set.seed","sample","sample.int",
    "ts","start","end","frequency","cycle","window",
    "aggregate","na.omit","na.fail","complete.cases","na.action",
    # dplyr / tidyr
    "filter","select","mutate","arrange","group_by",
    "summarise","summarize","rename","distinct","count",
    "left_join","right_join","inner_join","full_join",
    "anti_join","semi_join",
    "pivot_longer","pivot_wider","spread","gather",
    "bind_rows","bind_cols",
    "pull","slice","top_n","ungroup","rowwise",
    "transmute","case_when","if_else","coalesce",
    "lead","lag","between","near",
    "starts_with","ends_with","contains","matches",
    "everything","all_of","any_of","where",
    # ggplot2
    "ggplot","aes","aes_string",
    "geom_point","geom_line","geom_bar","geom_col",
    "geom_histogram","geom_boxplot","geom_violin",
    "geom_smooth","geom_ribbon","geom_area","geom_tile",
    "geom_text","geom_label","geom_hline","geom_vline","geom_abline",
    "geom_errorbar","geom_errorbarh","geom_crossbar",
    "geom_segment","geom_curve","geom_rect","geom_polygon",
    "scale_x_continuous","scale_y_continuous",
    "scale_x_log10","scale_y_log10",
    "scale_x_discrete","scale_y_discrete",
    "scale_color_manual","scale_colour_manual","scale_fill_manual",
    "scale_color_continuous","scale_fill_continuous",
    "scale_color_gradient","scale_fill_gradient",
    "coord_flip","coord_cartesian","coord_trans",
    "facet_wrap","facet_grid",
    "theme","theme_bw","theme_minimal","theme_classic",
    "theme_set","element_text","element_line","element_rect",
    "element_blank","unit",
    "labs","xlab","ylab","ggtitle",
    "guides","guide_legend","guide_colorbar","ggsave",
    # data.table
    "fread","fwrite","setDT","setDF","as.data.table",
    "rbindlist","setkey","setkeyv","setorder","setorderv",
    "setnames","setcolorder","copy","nafill",
    # stringr
    "str_detect","str_match","str_extract","str_replace",
    "str_split","str_trim","str_pad","str_wrap",
    "str_length","str_sub","str_c","str_glue",
    "str_count","str_locate","str_to_lower","str_to_upper",
    "str_remove","str_replace_all","str_remove_all",
    "str_starts","str_ends",
    # purrr
    "map","map_dbl","map_int","map_chr","map_lgl",
    "map_df","map_dfr","map_dfc","map2","pmap",
    "walk","walk2","pwalk",
    "reduce","accumulate","keep","discard","compact",
    "flatten","flatten_dbl","flatten_int","flatten_chr",
    "possibly","safely","quietly",
    "imap","lmap","modify","modify_if","modify_at",
    # lubridate
    "ymd","mdy","dmy","ymd_hms","now","today",
    "year","month","day","hour","minute","second",
    "days","weeks","months","years","hours","minutes",
    "interval","duration","period",
    "floor_date","ceiling_date","round_date",
    "with_tz","force_tz",
    # forcats
    "fct_relevel","fct_reorder","fct_rev","fct_drop",
    "fct_collapse","fct_lump","fct_other",
    # readr
    "read_csv","read_tsv","read_delim","read_fwf",
    "write_csv","write_tsv","write_delim",
    "cols","col_double","col_integer","col_character",
    "col_logical","col_factor","col_date",
    # lme4 / nlme
    "nlmer","lme","gls",
    "ranef","fixef","VarCorr",
    # survey
    "svydesign","svyglm","svymean","svytotal","svyquantile",
    "svychisq","svyttest","svyratio","svyciprop",
    # parallel
    "mclapply","mcmapply","detectCores","makeCluster","stopCluster",
    "parLapply","parSapply","parApply",
    "future","plan","future_map","future_lapply",
})

# ---------------------------------------------------------------------------
# Shared AST traversal helpers
# ---------------------------------------------------------------------------

def _is_definition_node(node: Any) -> bool:
    parent = node.parent
    if parent is None:
        return False
    pt = parent.type
    if pt in ("left_assignment", "equals_assignment", "super_assignment"):
        return bool(parent.children) and parent.children[0] == node
    if pt == "right_assignment":
        return bool(parent.children) and parent.children[-1] == node
    if pt == "formal_parameters":
        return True
    if pt == "default_parameter":
        return bool(parent.children) and parent.children[0] == node
    if pt == "for":
        found_in = False
        for child in parent.children:
            if child.type == "in":
                found_in = True
            if child == node:
                return not found_in
        return False
    return False


def _is_named_arg_key(node: Any) -> bool:
    parent = node.parent
    if parent is None or parent.type != "default_argument":
        return False
    kids = [c for c in parent.children if c.type != "="]
    return bool(kids) and kids[0] == node


def _is_namespace_access(node: Any) -> bool:
    parent = node.parent
    return parent is not None and parent.type in (
        "namespace_get", "namespace_get_internal"
    )


def _is_dollar_rhs(node: Any) -> bool:
    parent = node.parent
    if parent is None or parent.type not in ("dollar", "at"):
        return False
    kids = [c for c in parent.children if c.type not in ("$", "@")]
    return len(kids) >= 2 and kids[-1] == node


def _collect_definitions(tree_root: Any, dest: set[str]) -> None:
    def walk(node: Any) -> None:
        if node.type == "identifier" and _is_definition_node(node):
            dest.add(node.text.decode("utf-8", errors="replace"))
        for child in node.children:
            walk(child)
    walk(tree_root)


def _collect_uses(tree_root: Any) -> list[tuple[str, int]]:
    uses: list[tuple[str, int]] = []
    def walk(node: Any) -> None:
        if node.type == "identifier":
            if (not _is_definition_node(node)
                    and not _is_named_arg_key(node)
                    and not _is_namespace_access(node)
                    and not _is_dollar_rhs(node)):
                uses.append((
                    node.text.decode("utf-8", errors="replace"),
                    node.start_point[0] + 1,
                ))
        for child in node.children:
            walk(child)
    walk(tree_root)
    return uses


def _has_library_calls(tree_root: Any) -> bool:
    def walk(node: Any) -> bool:
        if (node.type == "identifier"
                and node.text in (b"library", b"require")
                and node.parent
                and node.parent.type == "call"):
            return True
        return any(walk(c) for c in node.children)
    return walk(tree_root)


# ---------------------------------------------------------------------------
# check_undefined_references
# ---------------------------------------------------------------------------

_MIN_NAME_LEN = 3
_MAX_EVIDENCE_PER_FILE = 5


def check_undefined_references(repo_path: Path, **_: object) -> CheckResult:
    """Flag identifiers used in expression position that are not defined
    anywhere in the repository and not part of base-R or common packages.

    Requires ``tree-sitter-languages``. Falls back to ``not_implemented``.

    Limitation: function-level scope is not tracked; library-imported names
    not in ``_WHITELIST`` may produce false positives when ``library()`` is
    absent from the file.
    """
    if not _AVAILABLE:
        return _not_impl_for("check_undefined_references")

    global_defs: set[str] = set()
    trees: dict[str, Any] = {}

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        source = read_text_safe(path).encode("utf-8", errors="replace")
        tree = _parse(source)
        if tree is None:
            continue
        rel = relpath(path, repo_path)
        trees[rel] = tree
        _collect_definitions(tree.root_node, global_defs)

    fail_evidence: list[dict] = []
    reported: set[tuple[str, str]] = set()

    for rel, tree in trees.items():
        has_lib = _has_library_calls(tree.root_node)
        min_len = 6 if has_lib else _MIN_NAME_LEN
        file_count = 0

        for name, lineno in _collect_uses(tree.root_node):
            if len(name) < min_len:
                continue
            if name in global_defs or name in _WHITELIST:
                continue
            key = (name, rel)
            if key in reported:
                continue
            reported.add(key)
            fail_evidence.append({
                "file": rel,
                "line": lineno,
                "note": f"'{name}' used but not defined in repository or base-R whitelist",
            })
            file_count += 1
            if file_count >= _MAX_EVIDENCE_PER_FILE:
                break

    if not fail_evidence:
        return CheckResult(
            tool_id="check_undefined_references",
            status="pass",
            summary=f"No undefined references detected (scanned {len(trees)} R file(s)).",
            evidence=[],
            metadata={"files_scanned": len(trees)},
        )
    return CheckResult(
        tool_id="check_undefined_references",
        status="fail",
        summary=f"{len(fail_evidence)} potentially undefined reference(s) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence), "files_scanned": len(trees)},
    )


# ---------------------------------------------------------------------------
# Shared helpers for function-level checks
# ---------------------------------------------------------------------------

def _extract_params(func_node: Any) -> tuple[set[str], bool]:
    params: set[str] = set()
    has_dots = False
    for child in func_node.children:
        if child.type != "formal_parameters":
            continue
        for param in child.children:
            if param.type == "dots":
                has_dots = True
            elif param.type == "identifier":
                name = param.text.decode("utf-8", errors="replace")
                if name == "...":
                    has_dots = True
                else:
                    params.add(name)
            elif param.type == "default_parameter" and param.children:
                name = param.children[0].text.decode("utf-8", errors="replace")
                if name == "...":
                    has_dots = True
                else:
                    params.add(name)
        break
    return params, has_dots


def _collect_func_defs(tree_root: Any) -> dict[str, tuple[set[str], bool, int]]:
    defs: dict[str, tuple[set[str], bool, int]] = {}
    def walk(node: Any) -> None:
        if node.type in ("left_assignment", "equals_assignment"):
            ch = node.children
            if (len(ch) >= 3
                    and ch[0].type == "identifier"
                    and ch[2].type == "function_definition"):
                name = ch[0].text.decode("utf-8", errors="replace")
                params, has_dots = _extract_params(ch[2])
                defs[name] = (params, has_dots, node.start_point[0] + 1)
        for c in node.children:
            walk(c)
    walk(tree_root)
    return defs


def _call_named_args(call_node: Any) -> list[str]:
    keys: list[str] = []
    for child in call_node.children:
        if child.type != "arguments":
            continue
        for arg in child.children:
            if arg.type == "default_argument":
                kw = [c for c in arg.children if c.type not in ("=", ",")]
                if kw and kw[0].type == "identifier":
                    keys.append(kw[0].text.decode("utf-8", errors="replace"))
        break
    return keys


def _call_positional_count(call_node: Any) -> int:
    count = 0
    for child in call_node.children:
        if child.type != "arguments":
            continue
        for arg in child.children:
            if arg.type not in ("default_argument", ",", "(", ")"):
                count += 1
        break
    return count


def _collect_called_names(tree_root: Any) -> set[str]:
    called: set[str] = set()
    def walk(node: Any) -> None:
        if node.type == "call":
            ch = node.children
            if ch and ch[0].type == "identifier":
                called.add(ch[0].text.decode("utf-8", errors="replace"))
        elif (node.type == "identifier"
              and node.parent
              and node.parent.type == "arguments"):
            called.add(node.text.decode("utf-8", errors="replace"))
        for c in node.children:
            walk(c)
    walk(tree_root)
    return called


# ---------------------------------------------------------------------------
# check_function_signatures
# ---------------------------------------------------------------------------

def _walk_sig(
    node: Any,
    cur_rel: str,
    func_defs: dict[str, tuple[set[str], bool, int]],
    evidence: list[dict],
) -> None:
    if node.type == "call":
        ch = node.children
        if ch and ch[0].type == "identifier":
            fname = ch[0].text.decode("utf-8", errors="replace")
            if fname in func_defs:
                params, has_dots, _ = func_defs[fname]
                if not has_dots:
                    bad = [k for k in _call_named_args(node) if k not in params]
                    if bad:
                        evidence.append({
                            "file": cur_rel,
                            "line": node.start_point[0] + 1,
                            "note": (
                                f"call to '{fname}': unknown named arg(s): "
                                f"{', '.join(sorted(bad))}"
                            ),
                        })
                    else:
                        pos = _call_positional_count(node)
                        named = len(_call_named_args(node))
                        if pos + named > len(params):
                            evidence.append({
                                "file": cur_rel,
                                "line": node.start_point[0] + 1,
                                "note": (
                                    f"call to '{fname}': {pos + named} arg(s) "
                                    f"but signature has {len(params)}"
                                ),
                            })
    for c in node.children:
        _walk_sig(c, cur_rel, func_defs, evidence)


def check_function_signatures(repo_path: Path, **_: object) -> CheckResult:
    """Flag call sites to locally-defined functions with mismatched arguments.

    Checks for unknown named arguments and too many positional arguments.
    Skips functions that accept ``...``. Only locally-defined functions are
    checked; library functions require a package DB and are out of scope.

    Requires ``tree-sitter-languages``. Falls back to ``not_implemented``.
    """
    if not _AVAILABLE:
        return _not_impl_for("check_function_signatures")

    all_defs: dict[str, tuple[set[str], bool, int]] = {}
    trees: dict[str, Any] = {}

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        source = read_text_safe(path).encode("utf-8", errors="replace")
        tree = _parse(source)
        if tree is None:
            continue
        rel = relpath(path, repo_path)
        trees[rel] = tree
        all_defs.update(_collect_func_defs(tree.root_node))

    fail_evidence: list[dict] = []
    for rel, tree in trees.items():
        _walk_sig(tree.root_node, rel, all_defs, fail_evidence)

    if not fail_evidence:
        return CheckResult(
            tool_id="check_function_signatures",
            status="pass",
            summary=f"No signature mismatches at {len(all_defs)} local function(s).",
            evidence=[],
            metadata={"local_functions_checked": len(all_defs)},
        )
    return CheckResult(
        tool_id="check_function_signatures",
        status="fail",
        summary=f"{len(fail_evidence)} call-site signature mismatch(es) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_dead_code
# ---------------------------------------------------------------------------

_ENTRY_POINT_NAMES: frozenset[str] = frozenset({
    "main","run","run_analysis","run_pipeline","render",
    "shinyApp","server","ui","app","knit","rmarkdown","test_that",
})


def check_dead_code(repo_path: Path, **_: object) -> CheckResult:
    """Flag locally-defined functions that are never called anywhere in the repo.

    Also counts identifiers passed as arguments to higher-order functions
    (e.g. ``lapply(x, helper)`` counts as calling ``helper``). Entry-point
    names (``main``, ``run_analysis``, ``shinyApp``, etc.) are whitelisted.

    Requires ``tree-sitter-languages``. Falls back to ``not_implemented``.
    """
    if not _AVAILABLE:
        return _not_impl_for("check_dead_code")

    all_defs: dict[str, tuple[str, int]] = {}
    all_called: set[str] = set()
    trees: list[tuple[str, Any]] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        source = read_text_safe(path).encode("utf-8", errors="replace")
        tree = _parse(source)
        if tree is None:
            continue
        rel = relpath(path, repo_path)
        trees.append((rel, tree))
        for name, (_params, _dots, lineno) in _collect_func_defs(tree.root_node).items():
            all_defs[name] = (rel, lineno)

    for _rel, tree in trees:
        all_called |= _collect_called_names(tree.root_node)

    fail_evidence: list[dict] = []
    for name, (rel, lineno) in sorted(all_defs.items()):
        if name in all_called or name in _ENTRY_POINT_NAMES:
            continue
        fail_evidence.append({
            "file": rel,
            "line": lineno,
            "note": f"Function '{name}' is defined but never called in the repository",
        })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_dead_code",
            status="pass",
            summary=f"All {len(all_defs)} locally-defined function(s) are reachable.",
            evidence=[],
            metadata={"local_functions": len(all_defs)},
        )
    return CheckResult(
        tool_id="check_dead_code",
        status="fail",
        summary=f"{len(fail_evidence)} potentially unused function(s) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_loop_invariants
# ---------------------------------------------------------------------------

_SIZE_FUNCS: frozenset[str] = frozenset({
    "length","nrow","ncol","dim","NROW","NCOL","nchar","lengths",
})


def _assigned_names_in_subtree(node: Any) -> set[str]:
    assigned: set[str] = set()
    def walk(n: Any) -> None:
        if n.type in ("left_assignment","equals_assignment","super_assignment"):
            ch = n.children
            if ch and ch[0].type == "identifier":
                assigned.add(ch[0].text.decode("utf-8", errors="replace"))
        for c in n.children:
            walk(c)
    walk(node)
    return assigned


def _get_for_loop_var(for_node: Any) -> str | None:
    found_in = False
    for child in for_node.children:
        if child.type == "in":
            found_in = True
        if not found_in and child.type == "identifier":
            return child.text.decode("utf-8", errors="replace")
    return None


def _first_arg(call_node: Any) -> Any | None:
    for child in call_node.children:
        if child.type != "arguments":
            continue
        for arg in child.children:
            if arg.type not in (",", "(", ")"):
                if arg.type == "default_argument":
                    vals = [c for c in arg.children if c.type != "="]
                    return vals[1] if len(vals) > 1 else None
                return arg
    return None


def _check_invariants_in_body(
    body: Any,
    cur_rel: str,
    loop_var: str | None,
    assigned_in_body: set[str],
    evidence: list[dict],
) -> None:
    def walk(n: Any) -> None:
        if n.type == "call":
            ch = n.children
            if ch and ch[0].type == "identifier":
                fname = ch[0].text.decode("utf-8", errors="replace")
                if fname in _SIZE_FUNCS:
                    first = _first_arg(n)
                    if first is not None and first.type == "identifier":
                        arg_name = first.text.decode("utf-8", errors="replace")
                        if arg_name != loop_var and arg_name not in assigned_in_body:
                            evidence.append({
                                "file": cur_rel,
                                "line": n.start_point[0] + 1,
                                "note": (
                                    f"'{fname}({arg_name})' is loop-invariant"
                                    " -- hoist before loop"
                                ),
                            })
        for c in n.children:
            walk(c)
    walk(body)


def _find_loops(node: Any, cur_rel: str, evidence: list[dict]) -> None:
    if node.type in ("for", "while"):
        loop_var = _get_for_loop_var(node) if node.type == "for" else None
        body: Any = None
        for child in node.children:
            if child.type in ("brace_list", "block"):
                body = child
                break
        if body is None and node.children:
            body = node.children[-1]
        if body is not None:
            assigned = _assigned_names_in_subtree(body)
            _check_invariants_in_body(body, cur_rel, loop_var, assigned, evidence)
    for c in node.children:
        _find_loops(c, cur_rel, evidence)


def check_loop_invariants(repo_path: Path, **_: object) -> CheckResult:
    """Flag size-computation calls (length/nrow/ncol/dim/...) inside loops
    whose argument does not change in the loop body.

    These computations are loop-invariant and should be hoisted before the loop
    to avoid repeated evaluation (O(N) -> O(1) for the size call).

    Requires ``tree-sitter-languages``. Falls back to ``not_implemented``.

    Limitation: only plain-identifier arguments are checked; expressions like
    ``length(x[i])`` are not flagged even if ``x`` is invariant.
    """
    if not _AVAILABLE:
        return _not_impl_for("check_loop_invariants")

    fail_evidence: list[dict] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        source = read_text_safe(path).encode("utf-8", errors="replace")
        tree = _parse(source)
        if tree is None:
            continue
        rel = relpath(path, repo_path)
        _find_loops(tree.root_node, rel, fail_evidence)

    if not fail_evidence:
        return CheckResult(
            tool_id="check_loop_invariants",
            status="pass",
            summary="No loop-invariant size computations detected.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_loop_invariants",
        status="fail",
        summary=f"{len(fail_evidence)} loop-invariant computation(s) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )
