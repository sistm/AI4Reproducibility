"""
Path-related static checks: absolute paths, setwd(), platform-independent helpers.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import CheckResult, iter_source_files, relpath, strip_inline_comment

# Absolute paths and setwd().
#   /home/..., /Users/..., C:\..., D:\..., setwd(...)
ABS_PATH_PATTERNS = [
    re.compile(r"""['"](/home/|/Users/|/mnt/|/data/|/opt/|/srv/|/tmp/)"""),
    re.compile(r"""['"][A-Za-z]:[\\/]"""),
    re.compile(r"\bsetwd\s*\("),
    re.compile(r"\bos\.chdir\s*\("),
]


def check_absolute_paths(repo_path: Path, **_: object) -> CheckResult:
    """bj-07-no-absolute-paths: no hard-coded absolute paths or setwd()."""
    offenders: list[dict] = []
    for path, lang in iter_source_files(repo_path, languages={"r", "python"}):
        for i, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            code = strip_inline_comment(raw)
            if not code.strip():
                continue
            for pat in ABS_PATH_PATTERNS:
                if pat.search(code):
                    offenders.append({
                        "file": relpath(path, repo_path),
                        "line": i,
                        "snippet": raw.strip()[:200],
                        "language": lang,
                    })
                    break

    return CheckResult(
        tool_id="check_absolute_paths",
        status="fail" if offenders else "pass",
        summary=(
            f"Found {len(offenders)} absolute-path or setwd()/chdir() occurrence(s)."
            if offenders
            else "No absolute paths or working-directory changes detected."
        ),
        evidence=offenders[:50],
        metadata={"total_violations": len(offenders)},
    )


# Hard-coded path separators outside file.path() / os.path.join() / pathlib.
# Imperfect heuristic: flag string literals that look like multi-segment paths
# with explicit separators.
PATH_HELPER_OK_R = re.compile(r"\b(file\.path|here|here::here)\s*\(")
PATH_HELPER_OK_PY = re.compile(r"\b(os\.path\.join|Path|pathlib\.Path|joinpath)\s*\(")
PATH_SEP_LITERAL_RE = re.compile(r"""['"][\w.\-]+[\\/][\w.\-]+[\\/][\w.\-]+['"]""")


def check_path_helpers(repo_path: Path, **_: object) -> CheckResult:
    """audit-repro-platform-independence: paths built with helpers, not literals."""
    offenders: list[dict] = []
    for path, lang in iter_source_files(repo_path, languages={"r", "python"}):
        helper_re = PATH_HELPER_OK_R if lang == "r" else PATH_HELPER_OK_PY
        for i, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            code = strip_inline_comment(raw)
            if not code.strip():
                continue
            # If the line uses a helper, assume any literal separator is fine.
            if helper_re.search(code):
                continue
            if PATH_SEP_LITERAL_RE.search(code):
                offenders.append({
                    "file": relpath(path, repo_path),
                    "line": i,
                    "snippet": raw.strip()[:200],
                    "language": lang,
                })

    return CheckResult(
        tool_id="check_path_helpers",
        status="warning" if offenders else "pass",
        summary=(
            f"{len(offenders)} line(s) use hard-coded path separators without a path helper."
            if offenders
            else "All multi-segment paths use platform-independent helpers."
        ),
        evidence=offenders[:50],
        metadata={"total_violations": len(offenders)},
    )
