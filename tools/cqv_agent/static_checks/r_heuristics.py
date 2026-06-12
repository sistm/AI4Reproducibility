"""
Regex-tractable static checks for R source code (patch 0071).

Five checks implementable in pure Python without an R AST parser. Each
returns a valid ``CheckResult`` with ``status="pass"|"fail"`` — never
``"not_implemented"``. Limitations are documented per-function; they are
known and acceptable given the regex-over-AST trade-off.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import (
    CheckResult,
    iter_source_files,
    read_text_safe,
    relpath,
    strip_inline_comment,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _start_depths(lines: list[str]) -> list[int]:
    """Return brace depth at the *start* of each line (before that line's
    braces are counted).  Used by loop and scope checks."""
    depths: list[int] = []
    depth = 0
    for line in lines:
        depths.append(depth)
        for ch in strip_inline_comment(line):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth = max(0, depth - 1)
    return depths


# ---------------------------------------------------------------------------
# check_set_seed_scope
# ---------------------------------------------------------------------------

_RNG_CALLS = (
    "runif(", "rnorm(", "sample(", "rbeta(", "rgamma(",
    "rpois(", "rexp(", "rbinom(",
)


def check_set_seed_scope(repo_path: Path, **_: object) -> CheckResult:
    """cqv-set-seed-scope: set.seed() must precede every RNG call in each file.

    Walk each ``.R`` file.  Find the first line containing ``set.seed(``.
    Find the first line containing any canonical RNG call.  If the RNG call
    appears before ``set.seed`` — or ``set.seed`` is absent — emit a fail
    evidence entry for that file.

    Limitation: misses ``set.seed`` in a ``source()``-d file.
    """
    fail_evidence: list[dict] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)
        seed_line: int | None = None
        rng_line: int | None = None

        for lineno, raw in enumerate(lines, 1):
            code = strip_inline_comment(raw)
            if seed_line is None and "set.seed(" in code:
                seed_line = lineno
            if rng_line is None and any(call in code for call in _RNG_CALLS):
                rng_line = lineno

        if rng_line is not None and (seed_line is None or rng_line < seed_line):
            note = (
                "RNG call appears before set.seed()"
                if seed_line is not None
                else "RNG call with no set.seed() in file"
            )
            fail_evidence.append({"file": rel, "line": rng_line, "note": note})

    if not fail_evidence:
        return CheckResult(
            tool_id="check_set_seed_scope",
            status="pass",
            summary="set.seed() precedes all RNG calls in every R file.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_set_seed_scope",
        status="fail",
        summary=(
            f"RNG call appears before or without set.seed() in "
            f"{len(fail_evidence)} file(s)."
        ),
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_imports_complete
# ---------------------------------------------------------------------------

_IMPORT_RE = re.compile(
    r"""\b(?:library|require)\s*\(\s*["']?([\w.][\w.]*)["']?\s*\)"""
)
_NAMESPACE_RE = re.compile(r"""\b([\w.][\w.]*)::\w+""")


def check_imports_complete(repo_path: Path, **_: object) -> CheckResult:
    """cqv-imports-complete: every ``pkg::fn`` use must have a library() call.

    Collect all ``library(pkg)`` / ``require(pkg)`` declarations across all
    ``.R`` files.  For each package used via ``pkg::fn`` without a matching
    declaration, emit a fail evidence entry pointing to its first use.

    Limitation: misses packages accessed via base R without ``::`` qualification;
    does not special-case always-attached packages (base, stats, utils, methods).
    """
    declared: set[str] = set()
    first_use: dict[str, tuple[str, int]] = {}  # pkg -> (rel_path, lineno)

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)
        for lineno, raw in enumerate(lines, 1):
            code = strip_inline_comment(raw)
            for m in _IMPORT_RE.finditer(code):
                declared.add(m.group(1))
            for m in _NAMESPACE_RE.finditer(code):
                pkg = m.group(1)
                if pkg not in first_use:
                    first_use[pkg] = (rel, lineno)

    undeclared = {pkg: loc for pkg, loc in first_use.items() if pkg not in declared}

    if not undeclared:
        return CheckResult(
            tool_id="check_imports_complete",
            status="pass",
            summary=(
                "All namespace-qualified (::) packages have a "
                "library()/require() declaration."
            ),
            evidence=[],
        )

    evidence = [
        {
            "file": rel,
            "line": lineno,
            "note": (
                f"Package '{pkg}' used via '::' but not declared with "
                "library()/require()"
            ),
        }
        for pkg, (rel, lineno) in sorted(undeclared.items())
    ]
    return CheckResult(
        tool_id="check_imports_complete",
        status="fail",
        summary=(
            f"{len(evidence)} package(s) used via '::' without a "
            "library()/require() declaration."
        ),
        evidence=evidence[:50],
        metadata={"undeclared_packages": sorted(undeclared)},
    )


# ---------------------------------------------------------------------------
# check_function_docs_present
# ---------------------------------------------------------------------------

_FUNC_DEF_RE = re.compile(r"""(?:<-|=)\s*function\s*\(""")


def check_function_docs_present(repo_path: Path, **_: object) -> CheckResult:
    """cqv-function-docs: every function definition must be preceded by a comment.

    For each ``foo <- function(...)`` or ``foo = function(...)`` definition,
    check whether the immediately-preceding non-blank line is a ``#``-prefixed
    comment.  If not, emit a fail evidence entry.

    Limitation: does not validate comment content; boilerplate (``# TODO``)
    satisfies the check.  Anonymous functions and single-expression functions
    without braces are included.
    """
    fail_evidence: list[dict] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)

        for i, raw in enumerate(lines):
            code = strip_inline_comment(raw)
            if not _FUNC_DEF_RE.search(code):
                continue

            func_lineno = i + 1  # 1-indexed
            # Find the immediately preceding non-blank line.
            prev_content: str | None = None
            for j in range(i - 1, -1, -1):
                if lines[j].strip():
                    prev_content = lines[j].strip()
                    break

            if prev_content is None or not prev_content.startswith("#"):
                fail_evidence.append({
                    "file": rel,
                    "line": func_lineno,
                    "note": "Function definition not preceded by a # comment",
                })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_function_docs_present",
            status="pass",
            summary="All function definitions are preceded by a comment.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_function_docs_present",
        status="fail",
        summary=(
            f"{len(fail_evidence)} function definition(s) lack a preceding comment."
        ),
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_no_unbounded_loops
# ---------------------------------------------------------------------------

_LOOP_RE = re.compile(r"""\bwhile\s*\(\s*T(?:RUE)?\s*\)|\brepeat\b""")
_BREAK_RE = re.compile(r"""\bbreak\b""")


def check_no_unbounded_loops(repo_path: Path, **_: object) -> CheckResult:
    """cqv-no-unbounded-loops: while(TRUE) and repeat must contain a break.

    Find each ``while(TRUE)``, ``while(T)``, or ``repeat`` keyword.  Count
    brace depth from that line; scan forward to the line that closes back to
    the opening depth.  If no ``break`` appears in that range, emit a fail
    evidence entry.

    Limitation: commented-out ``break``s satisfy the check; a ``break``
    inside a nested inner loop is sufficient even though it only exits that
    inner loop.
    """
    fail_evidence: list[dict] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)
        n = len(lines)
        start_depths = _start_depths(lines)

        for i, raw in enumerate(lines):
            code = strip_inline_comment(raw)
            if not _LOOP_RE.search(code):
                continue

            loop_lineno = i + 1
            initial_depth = start_depths[i]
            depth = initial_depth
            body_started = False
            has_break = False

            for j in range(i, n):
                scan = strip_inline_comment(lines[j])

                if _BREAK_RE.search(scan):
                    has_break = True

                for ch in scan:
                    if ch == "{":
                        depth += 1
                        body_started = True
                    elif ch == "}":
                        depth = max(0, depth - 1)

                if body_started and depth <= initial_depth:
                    break

            if not has_break:
                fail_evidence.append({
                    "file": rel,
                    "line": loop_lineno,
                    "note": "Potentially unbounded loop: no 'break' in loop body",
                })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_no_unbounded_loops",
            status="pass",
            summary="No unbounded while(TRUE)/repeat loops detected.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_no_unbounded_loops",
        status="fail",
        summary=f"{len(fail_evidence)} potentially unbounded loop(s) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_global_state_mutation
# ---------------------------------------------------------------------------

_SUPERASSIGN_RE = re.compile(r"""<<-""")
_FUNC_OPEN_RE = re.compile(r"""\bfunction\s*\(""")


def check_global_state_mutation(repo_path: Path, **_: object) -> CheckResult:
    """cqv-global-state-mutation: <<- only inside function bodies.

    Find each ``<<-`` operator.  Search backward through already-scanned
    lines for a ``function(`` that appears at lower brace depth.  If none
    is found (i.e. ``<<-`` at module top-level), emit a fail evidence entry.

    Limitation: ``local({...})`` closures are not distinguished from module
    scope; a ``function(`` that appears at the same depth as ``<<-`` is not
    counted.
    """
    fail_evidence: list[dict] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)
        start_depths = _start_depths(lines)

        for i, raw in enumerate(lines):
            code = strip_inline_comment(raw)
            if not _SUPERASSIGN_RE.search(code):
                continue

            cur_depth = start_depths[i]
            inside_func = False
            for j in range(i - 1, -1, -1):
                prev_code = strip_inline_comment(lines[j])
                if (
                    _FUNC_OPEN_RE.search(prev_code)
                    and start_depths[j] < cur_depth
                ):
                    inside_func = True
                    break

            if not inside_func:
                fail_evidence.append({
                    "file": rel,
                    "line": i + 1,
                    "note": "<<- at module top-level (no enclosing function at lower brace depth)",
                })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_global_state_mutation",
            status="pass",
            summary="No top-level <<- operators detected.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_global_state_mutation",
        status="fail",
        summary=f"{len(fail_evidence)} top-level <<- operator(s) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )
