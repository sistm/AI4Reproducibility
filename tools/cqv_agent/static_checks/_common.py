"""
Shared utilities for CQV static checks.

Every static check returns a ``CheckResult``. Checks scan a repository for
patterns or files; they do not write to disk or call out to LLMs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal

# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

CheckStatus = Literal["pass", "fail", "warning", "not_applicable", "not_implemented"]


@dataclass
class CheckResult:
    """Outcome of a single static check.

    Attributes:
        tool_id:   The static-check tool name (e.g. "check_absolute_paths").
        status:    pass / fail / warning / not_applicable / not_implemented.
        summary:   One-line human-readable summary.
        evidence:  List of evidence dicts. Each typically has keys:
                   ``file``, ``line`` (optional), ``snippet`` (optional),
                   ``kind`` (optional).
        metadata:  Free-form diagnostic info (counts, paths, etc.).
    """

    tool_id: str
    status: CheckStatus
    summary: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "summary": self.summary,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Language and file discovery
# ---------------------------------------------------------------------------

LANG_EXTENSIONS: dict[str, set[str]] = {
    "r":      {".r", ".R", ".Rmd", ".qmd"},
    "python": {".py", ".pyx"},
    "stata":  {".do", ".ado"},
    "julia":  {".jl"},
    "matlab": {".m"},
}

DEFAULT_EXCLUDE_DIRS: set[str] = {
    ".git", ".svn", ".hg",
    "node_modules",
    "venv", ".venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".ipynb_checkpoints",
    "renv/library", "renv/cellar", "renv/staging",
    "packrat/lib", "packrat/lib-R",
    "build", "dist", ".tox",
}

MAX_FILE_BYTES = 1_000_000  # skip files larger than 1 MB; they're unlikely to be source


def detect_language(path: Path) -> str | None:
    """Return the canonical language name for a file path, or None if unknown."""
    suffix = path.suffix
    for lang, exts in LANG_EXTENSIONS.items():
        if suffix in exts:
            return lang
    return None


def iter_source_files(
    repo_path: Path,
    languages: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
) -> Iterator[tuple[Path, str]]:
    """Yield ``(path, language)`` for every source file under ``repo_path``.

    Skips excluded directories and files larger than ``MAX_FILE_BYTES``.
    """
    languages = languages or set(LANG_EXTENSIONS)
    exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS

    # Pre-compute substring matches for path components.
    exclude_parts = {p.split("/")[0] for p in exclude_dirs}
    exclude_subpaths = {p for p in exclude_dirs if "/" in p}

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded directories by examining path components.
        rel_parts = set(path.relative_to(repo_path).parts)
        if rel_parts & exclude_parts:
            continue
        rel_str = str(path.relative_to(repo_path)).replace("\\", "/")
        if any(sub in rel_str for sub in exclude_subpaths):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        lang = detect_language(path)
        if lang is None or lang not in languages:
            continue
        yield path, lang


def read_text_safe(path: Path) -> str:
    """Read a file as text with permissive decoding; return empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Line scanning helpers
# ---------------------------------------------------------------------------

def strip_inline_comment(line: str, comment_char: str = "#") -> str:
    """Return the line with any trailing comment stripped.

    Naive: does not handle ``#`` inside string literals. Good enough for
    pattern detection where false positives are rare and tolerable.
    """
    # Look for comment_char not preceded by a backslash and not inside
    # a simple quoted region.
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == comment_char and not in_single and not in_double:
            return line[:i]
    return line


def relpath(path: Path, root: Path) -> str:
    """Return path relative to root, with forward slashes for portability."""
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
