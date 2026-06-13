"""
Cross-language static checks implementable without a language AST parser (patch 0092).

Four checks that were incorrectly classified as "AST-requiring":

* check_parse_success       — Python: stdlib ast.parse(); R: delimiter balance.
* check_duplicate_code_blocks — sliding-window literal-hash comparison.
* check_growing_vectors     — regex backreference catches c(vec, …)/append(vec, …) in loops.
* check_error_handling_coverage — network/external ops without any tryCatch in file.

The remaining four stubs (check_undefined_references, check_function_signatures,
check_dead_code, check_loop_invariants) genuinely need a symbol table or CFG;
they stay in _stubs.py until tree-sitter-r is integrated.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._common import (
    CheckResult,
    iter_source_files,
    read_text_safe,
    relpath,
    strip_inline_comment,
)
from .r_heuristics import _start_depths  # reuse brace-depth helper

# ---------------------------------------------------------------------------
# check_parse_success
# ---------------------------------------------------------------------------

def check_parse_success(repo_path: Path, **_: object) -> CheckResult:
    """Parse every source file; emit fail evidence for files with syntax errors.

    Python — uses :func:`ast.parse` (exact).
    R — checks brace/parenthesis/bracket balance; catches unclosed delimiters
    and negative depth. Limitation: string literals containing unmatched
    delimiters can produce false positives; single-quote strings are skipped
    when the opening quote appears on the same line.
    """
    fail_evidence: list[dict] = []

    for path, lang in iter_source_files(repo_path, languages={"python", "r"}):
        source = read_text_safe(path)
        rel = relpath(path, repo_path)

        if lang == "python":
            try:
                ast.parse(source)
            except SyntaxError as exc:
                fail_evidence.append({
                    "file": rel,
                    "line": exc.lineno or 0,
                    "note": f"Python SyntaxError: {exc.msg}",
                })

        elif lang == "r":
            depth = {"brace": 0, "paren": 0, "bracket": 0}
            _open = {"{": "brace", "(": "paren", "[": "bracket"}
            _close = {"}": "brace", ")": "paren", "]": "bracket"}
            error_line: int | None = None

            for lineno, raw in enumerate(source.splitlines(), 1):
                # Strip comments; naively skip string content.
                code = strip_inline_comment(raw)
                in_str: str | None = None
                for ch in code:
                    if in_str:
                        if ch == in_str:
                            in_str = None
                    elif ch in ('"', "'"):
                        in_str = ch
                    elif ch in _open:
                        depth[_open[ch]] += 1
                    elif ch in _close:
                        depth[_close[ch]] -= 1
                        if depth[_close[ch]] < 0:
                            error_line = lineno
                            break
                if error_line:
                    break

            if error_line is not None:
                fail_evidence.append({
                    "file": rel,
                    "line": error_line,
                    "note": "Unmatched closing delimiter (brace/paren/bracket depth went negative)",
                })
            elif any(v != 0 for v in depth.values()):
                last = len(source.splitlines())
                fail_evidence.append({
                    "file": rel,
                    "line": last,
                    "note": (
                        f"Unclosed delimiter(s) at end of file "
                        f"(brace={depth['brace']}, "
                        f"paren={depth['paren']}, "
                        f"bracket={depth['bracket']})"
                    ),
                })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_parse_success",
            status="pass",
            summary="All source files pass delimiter-balance / syntax check.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_parse_success",
        status="fail",
        summary=f"Syntax / delimiter errors in {len(fail_evidence)} file(s).",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_duplicate_code_blocks
# ---------------------------------------------------------------------------

_MIN_BLOCK_LINES = 6    # minimum window of non-trivial lines
_MIN_LINE_LEN = 20      # lines shorter than this don't count toward the minimum
_MIN_SEPARATION = 15    # two occurrences in the same file must be ≥ N lines apart


def _norm(line: str) -> str:
    return strip_inline_comment(line).strip()


def check_duplicate_code_blocks(repo_path: Path, **_: object) -> CheckResult:
    """Detect copy-pasted code blocks via sliding-window normalised-line hashing.

    A *block* is a window of ``_MIN_BLOCK_LINES`` non-trivial lines (each ≥
    ``_MIN_LINE_LEN`` chars after stripping comments and whitespace). Two
    occurrences of the same block — in the same file ≥ ``_MIN_SEPARATION``
    lines apart, or in different files — trigger a fail evidence entry.

    Limitation: only detects literal duplicates (copy-paste); semantic
    duplicates with renamed variables require AST-level comparison.
    """
    # {block_tuple: [(rel_path, start_lineno_1indexed)]}
    seen: dict[tuple[str, ...], list[tuple[str, int]]] = {}

    for path, _lang in iter_source_files(repo_path, languages={"python", "r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)
        normed = [_norm(ln) for ln in lines]

        # Indices of non-trivial lines
        nt = [i for i, ln in enumerate(normed) if len(ln) >= _MIN_LINE_LEN]
        if len(nt) < _MIN_BLOCK_LINES:
            continue

        for i in range(len(nt) - _MIN_BLOCK_LINES + 1):
            idx = nt[i: i + _MIN_BLOCK_LINES]
            # Reject windows where lines are too spread out (scattered, not a block)
            if idx[-1] - idx[0] > _MIN_BLOCK_LINES * 4:
                continue
            block: tuple[str, ...] = tuple(normed[j] for j in idx)
            seen.setdefault(block, []).append((rel, idx[0] + 1))

    fail_evidence: list[dict] = []
    reported: set[tuple[str, ...]] = set()

    for block, locs in seen.items():
        if len(locs) < 2 or block in reported:
            continue
        for i, (f1, l1) in enumerate(locs):
            for f2, l2 in locs[i + 1:]:
                if f1 != f2 or abs(l2 - l1) >= _MIN_SEPARATION:
                    fail_evidence.append({
                        "file": f1,
                        "line": l1,
                        "note": (
                            f"Duplicate {_MIN_BLOCK_LINES}-line block "
                            f"also found at {f2}:{l2}"
                        ),
                    })
                    reported.add(block)
                    break
            if block in reported:
                break

    if not fail_evidence:
        return CheckResult(
            tool_id="check_duplicate_code_blocks",
            status="pass",
            summary=f"No duplicate code blocks (≥{_MIN_BLOCK_LINES} lines) detected.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_duplicate_code_blocks",
        status="fail",
        summary=f"{len(fail_evidence)} duplicate code block(s) detected.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_growing_vectors
# ---------------------------------------------------------------------------

# Matches: varname <- c(varname, …)  or  append(varname, …)
# The \1 backreference enforces same variable name on both sides.
_VEC_GROW_RE = re.compile(
    r'\b([\w.]+)\s*(?:<-|=)\s*(?:c|append)\s*\(\s*\1\b'
)
_LOOP_START_RE = re.compile(r'\b(?:for|while)\s*\(')


def check_growing_vectors(repo_path: Path, **_: object) -> CheckResult:
    """Detect R vectors grown inside loops via ``c(vec, …)`` or ``append(vec, …)``.

    Pattern: inside a ``for``/``while`` loop, ``x <- c(x, item)`` or
    ``append(x, item)`` where ``x`` is the same variable being extended.
    This is O(N²) in R; pre-allocation or ``list + do.call(c, …)`` is the
    correct idiom.

    Limitation: detects only the literal same-variable pattern; aliased
    growing (``tmp <- c(x, item); x <- tmp``) is not detected without AST.
    """
    fail_evidence: list[dict] = []

    for path, _lang in iter_source_files(repo_path, languages={"r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)
        start_depths = _start_depths(lines)

        loop_depth_stack: list[int] = []

        for i, raw in enumerate(lines):
            code = strip_inline_comment(raw)
            cur = start_depths[i]

            # Pop any loops whose body depth we've fallen below
            while loop_depth_stack and cur < loop_depth_stack[-1]:
                loop_depth_stack.pop()

            # Detect new loop; its body starts at cur+1 (after the {)
            if _LOOP_START_RE.search(code):
                loop_depth_stack.append(cur + 1)

            # Flag growing-vector patterns inside an active loop
            if loop_depth_stack and cur >= loop_depth_stack[-1]:
                if _VEC_GROW_RE.search(code):
                    fail_evidence.append({
                        "file": rel,
                        "line": i + 1,
                        "note": (
                            "O(N²) vector growing in loop: use pre-allocated "
                            "vector or list + do.call(c, …) instead"
                        ),
                    })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_growing_vectors",
            status="pass",
            summary="No O(N²) vector-growing patterns detected inside loops.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_growing_vectors",
        status="fail",
        summary=f"{len(fail_evidence)} growing-vector pattern(s) inside loops.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )


# ---------------------------------------------------------------------------
# check_error_handling_coverage
# ---------------------------------------------------------------------------

# Network / external resource calls that should be wrapped in error handlers.
# Deliberately conservative: file I/O (read.csv etc.) is excluded because
# it is so common in analysis scripts that file-level flagging produces
# unacceptable false-positive rates. Only external network/HTTP ops are flagged.
_R_NETWORK_OPS: tuple[str, ...] = (
    "download.file(",
    "httr::", "httr2::",
    "curl::", "RCurl::",
    "rvest::",
    "xml2::read_html(",
    "jsonlite::fromJSON(",   # when fetching from URL
)
_R_HANDLERS: tuple[str, ...] = (
    "tryCatch(",
    "withCallingHandlers(",
    "try(",
)

_PY_NETWORK_OPS: tuple[str, ...] = (
    "requests.get(",
    "requests.post(",
    "requests.put(",
    "urllib.request.",
    "httpx.",
    "aiohttp.",
)
_PY_HANDLERS: tuple[str, ...] = (
    "try:",
    "except ",
    "with contextlib",
)


def check_error_handling_coverage(repo_path: Path, **_: object) -> CheckResult:
    """Flag source files that make external network calls without any error handler.

    Conservative scope: only external HTTP / network operations are checked,
    not file I/O (which is ubiquitous in analysis scripts and rarely requires
    a handler). A file-level presence of ``tryCatch`` / ``try`` (R) or a
    ``try:`` / ``except`` block (Python) is sufficient to pass.

    Limitation: does not verify the handler *wraps* the risky call; a
    ``tryCatch`` anywhere in the file satisfies the check. Per-call scope
    tracking requires AST.
    """
    fail_evidence: list[dict] = []

    for path, lang in iter_source_files(repo_path, languages={"python", "r"}):
        lines = read_text_safe(path).splitlines()
        rel = relpath(path, repo_path)

        if lang == "r":
            risky = _R_NETWORK_OPS
            handlers = _R_HANDLERS
        else:
            risky = _PY_NETWORK_OPS
            handlers = _PY_HANDLERS

        risky_lines: list[int] = []
        has_handler = False

        for lineno, raw in enumerate(lines, 1):
            code = strip_inline_comment(raw)
            if any(op in code for op in risky):
                risky_lines.append(lineno)
            if any(h in code for h in handlers):
                has_handler = True

        if risky_lines and not has_handler:
            fail_evidence.append({
                "file": rel,
                "line": risky_lines[0],
                "note": (
                    f"{len(risky_lines)} external network call(s) with no "
                    "error handler (tryCatch/try) in file"
                ),
            })

    if not fail_evidence:
        return CheckResult(
            tool_id="check_error_handling_coverage",
            status="pass",
            summary="All files with network calls have at least one error handler.",
            evidence=[],
        )
    return CheckResult(
        tool_id="check_error_handling_coverage",
        status="fail",
        summary=f"{len(fail_evidence)} file(s) with unguarded network calls.",
        evidence=fail_evidence[:50],
        metadata={"total_violations": len(fail_evidence)},
    )
