"""
File-inventory checks: existence, naming, and content of well-known files.

These are the simplest tier of static checks — they walk the repository,
look for files at conventional locations, and report what they find.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import CheckResult, iter_source_files, read_text_safe, relpath


# ---------------------------------------------------------------------------
# Documentation: README and sessionInfo
# ---------------------------------------------------------------------------

README_NAMES = ["README.md", "README.txt", "README.pdf", "README.Rmd", "README.rst",
                "readme.md", "readme.txt", "readme.pdf"]
SESSIONINFO_RE = re.compile(r"\bsessionInfo\s*\(", re.IGNORECASE)


def check_readme_present(repo_path: Path, **_: object) -> CheckResult:
    """bj-01-readme: README file at the repo root, ideally with sessionInfo."""
    found = [repo_path / n for n in README_NAMES if (repo_path / n).is_file()]
    if not found:
        return CheckResult(
            tool_id="check_readme_present",
            status="fail",
            summary="No README file found at the repository root.",
            evidence=[{"kind": "missing", "searched": README_NAMES}],
        )

    readme = found[0]
    text = read_text_safe(readme)
    has_sessioninfo = bool(SESSIONINFO_RE.search(text))

    return CheckResult(
        tool_id="check_readme_present",
        status="pass" if has_sessioninfo else "warning",
        summary=(
            f"README present at {relpath(readme, repo_path)}"
            + ("; sessionInfo block detected." if has_sessioninfo else
               "; no sessionInfo block detected (recommended for R submissions).")
        ),
        evidence=[{
            "file": relpath(readme, repo_path),
            "size_bytes": readme.stat().st_size,
            "has_sessioninfo": has_sessioninfo,
        }],
        metadata={"all_readmes_found": [relpath(p, repo_path) for p in found]},
    )


def check_sessioninfo_block(repo_path: Path, **_: object) -> CheckResult:
    """audit-doc-sessioninfo-r: R-specific check that sessionInfo or renv.lock is present."""
    readme_with_si: list[str] = []
    for name in README_NAMES:
        p = repo_path / name
        if p.is_file() and SESSIONINFO_RE.search(read_text_safe(p)):
            readme_with_si.append(relpath(p, repo_path))

    renv_lock = repo_path / "renv.lock"
    has_renv = renv_lock.is_file()

    if not readme_with_si and not has_renv:
        return CheckResult(
            tool_id="check_sessioninfo_block",
            status="fail",
            summary="Neither sessionInfo() in README nor renv.lock found.",
            evidence=[{"kind": "missing"}],
        )

    evidence: list[dict] = []
    for p in readme_with_si:
        evidence.append({"file": p, "kind": "sessioninfo_in_readme"})
    if has_renv:
        evidence.append({"file": "renv.lock", "kind": "renv_lockfile"})

    return CheckResult(
        tool_id="check_sessioninfo_block",
        status="pass",
        summary=(
            "R environment recorded via "
            + ("renv.lock" if has_renv else "")
            + (" and " if has_renv and readme_with_si else "")
            + (f"sessionInfo in {readme_with_si[0]}" if readme_with_si else "")
            + "."
        ),
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Python requirements + version pinning
# ---------------------------------------------------------------------------

PIN_RE = re.compile(r"==|>=|~=|<=")
UNPINNED_COMMENT_RE = re.compile(r"^\s*(#|$)")


def check_python_requirements(repo_path: Path, **_: object) -> CheckResult:
    """audit-doc-requirements-python: requirements.txt / environment.yml present."""
    candidates = ["requirements.txt", "requirements.in", "environment.yml",
                  "environment.yaml", "pyproject.toml", "Pipfile", "uv.lock", "poetry.lock"]
    found = [c for c in candidates if (repo_path / c).is_file()]

    if not found:
        return CheckResult(
            tool_id="check_python_requirements",
            status="fail",
            summary="No Python dependency manifest found.",
            evidence=[{"kind": "missing", "searched": candidates}],
        )

    # If requirements.txt exists, also check pinning quality.
    pin_evidence: list[dict] = []
    req = repo_path / "requirements.txt"
    if req.is_file():
        unpinned: list[str] = []
        for ln in read_text_safe(req).splitlines():
            if UNPINNED_COMMENT_RE.match(ln):
                continue
            if not PIN_RE.search(ln):
                unpinned.append(ln.strip())
        pin_evidence.append({
            "file": "requirements.txt",
            "unpinned_packages": unpinned,
        })

    return CheckResult(
        tool_id="check_python_requirements",
        status="pass",
        summary=f"Dependency manifests found: {', '.join(found)}.",
        evidence=[{"file": f, "kind": "dependency_manifest"} for f in found] + pin_evidence,
    )


def check_version_pinning(repo_path: Path, **_: object) -> CheckResult:
    """cqv-dep-versions-pinned: requirements.txt / renv.lock pin versions."""
    findings: list[dict] = []
    severity_fail = False

    req = repo_path / "requirements.txt"
    if req.is_file():
        unpinned: list[str] = []
        for ln in read_text_safe(req).splitlines():
            if UNPINNED_COMMENT_RE.match(ln):
                continue
            if not PIN_RE.search(ln):
                unpinned.append(ln.strip())
        if unpinned:
            severity_fail = True
        findings.append({"file": "requirements.txt", "unpinned": unpinned})

    renv = repo_path / "renv.lock"
    if renv.is_file():
        findings.append({"file": "renv.lock", "kind": "renv_lockfile_present"})

    pyproject = repo_path / "pyproject.toml"
    if pyproject.is_file():
        findings.append({"file": "pyproject.toml", "kind": "pyproject_present",
                         "note": "version pinning of pyproject deps not inspected by this check"})

    if not findings:
        return CheckResult(
            tool_id="check_version_pinning",
            status="fail",
            summary="No dependency manifest found to inspect for pinning.",
            evidence=[],
        )

    return CheckResult(
        tool_id="check_version_pinning",
        status="fail" if severity_fail else "pass",
        summary=(
            f"Unpinned packages found in {len([f for f in findings if f.get('unpinned')])} file(s)."
            if severity_fail
            else "All inspected dependency declarations are pinned."
        ),
        evidence=findings,
    )


# ---------------------------------------------------------------------------
# Environment tooling, main entry point, test directory
# ---------------------------------------------------------------------------

ENV_TOOLING_FILES = [
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "renv.lock", "environment.yml", "environment.yaml",
    "uv.lock", "poetry.lock", "Pipfile.lock",
    ".python-version", "runtime.txt",
]


def check_environment_tooling(repo_path: Path, **_: object) -> CheckResult:
    """audit-doc-env-tool: report which environment-reproducibility files exist."""
    found = [f for f in ENV_TOOLING_FILES if (repo_path / f).is_file()]
    return CheckResult(
        tool_id="check_environment_tooling",
        status="pass" if found else "warning",
        summary=(
            f"Environment tooling detected: {', '.join(found)}."
            if found
            else "No environment-reproducibility tooling detected (suggestion only)."
        ),
        evidence=[{"file": f, "kind": "env_tool"} for f in found],
    )


ENTRY_POINT_NAMES = [
    "main.R", "main.r", "main.py", "master.py", "master.R",
    "run.py", "run.R", "run_all.sh", "run_all.py", "run_all.R",
    "Makefile", "makefile", "_targets.R",
]


def check_main_entry_point(repo_path: Path, **_: object) -> CheckResult:
    """audit-org-main-entry-point: single-entry-point script exists."""
    found: list[str] = []
    # Search depth 1 for top-level entry points only.
    for name in ENTRY_POINT_NAMES:
        for match in repo_path.glob(name):
            if match.is_file():
                found.append(relpath(match, repo_path))
        for match in repo_path.glob(f"*/{name}"):
            if match.is_file():
                found.append(relpath(match, repo_path))

    if not found:
        return CheckResult(
            tool_id="check_main_entry_point",
            status="fail",
            summary="No conventional entry-point script found.",
            evidence=[{"kind": "missing", "searched": ENTRY_POINT_NAMES}],
        )

    return CheckResult(
        tool_id="check_main_entry_point",
        status="pass",
        summary=f"Entry-point script(s) found: {', '.join(found[:3])}"
                + ("..." if len(found) > 3 else "."),
        evidence=[{"file": f, "kind": "entry_point"} for f in found],
    )


def check_test_directory_present(repo_path: Path, **_: object) -> CheckResult:
    """cqv-test-suite-exists: test directory or test files exist."""
    found_dirs: list[str] = []
    for d in ("tests", "test"):
        p = repo_path / d
        if p.is_dir() and any(p.iterdir()):
            found_dirs.append(d)

    # R-style tests
    testthat = list(repo_path.rglob("tests/testthat"))
    if testthat:
        found_dirs.extend(relpath(t, repo_path) for t in testthat)

    # Python files matching test_*.py / *_test.py at any depth
    test_files: list[str] = []
    for pattern in ("test_*.py", "*_test.py"):
        for p in repo_path.rglob(pattern):
            test_files.append(relpath(p, repo_path))

    if not found_dirs and not test_files:
        return CheckResult(
            tool_id="check_test_directory_present",
            status="fail",
            summary="No test directory or test files found (suggestion-severity for research code).",
            evidence=[],
            metadata={"searched_dirs": ["tests/", "test/", "**/testthat/"],
                      "searched_patterns": ["test_*.py", "*_test.py"]},
        )

    return CheckResult(
        tool_id="check_test_directory_present",
        status="pass",
        summary=(
            f"Test directories: {found_dirs or 'none'}; "
            f"test files: {len(test_files)}."
        ),
        evidence=(
            [{"path": d, "kind": "test_directory"} for d in found_dirs]
            + [{"path": f, "kind": "test_file"} for f in test_files[:20]]
        ),
        metadata={"n_test_files": len(test_files)},
    )


# ---------------------------------------------------------------------------
# File naming hygiene
# ---------------------------------------------------------------------------

BAD_NAME_PATTERNS = [
    (re.compile(r"^x\d+\."), "starts with x<digits> (e.g. x001.R)"),
    (re.compile(r"^untitled", re.IGNORECASE), "named 'untitled'"),
    (re.compile(r"^copy[\s_-]of[\s_-]", re.IGNORECASE), "named 'copy of'"),
    (re.compile(r"\s"), "contains whitespace"),
    (re.compile(r"^new[\s_-]?\w+\.\w+$", re.IGNORECASE), "starts with 'new '"),
]


def check_file_naming_hygiene(repo_path: Path, **_: object) -> CheckResult:
    """audit-org-file-naming: descriptive names, no whitespace."""
    offenders: list[dict] = []
    for path, _lang in iter_source_files(repo_path):
        name = path.name
        for pattern, reason in BAD_NAME_PATTERNS:
            if pattern.search(name):
                offenders.append({
                    "file": relpath(path, repo_path),
                    "reason": reason,
                })
                break

    return CheckResult(
        tool_id="check_file_naming_hygiene",
        status="fail" if offenders else "pass",
        summary=(
            f"{len(offenders)} file(s) violate naming policy."
            if offenders
            else "All source-file names pass the naming policy."
        ),
        evidence=offenders,
    )


# ---------------------------------------------------------------------------
# Archive layout (assumes archive is already extracted to repo_path)
# ---------------------------------------------------------------------------

CLUTTER_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
CLUTTER_DIR_NAMES = {"__pycache__", ".ipynb_checkpoints", ".Rhistory"}


def check_archive_layout(repo_path: Path, **_: object) -> CheckResult:
    """bj-12-single-zip: report clutter remaining after extraction."""
    clutter: list[str] = []
    for path in repo_path.rglob("*"):
        if path.name in CLUTTER_NAMES:
            clutter.append(relpath(path, repo_path))
        elif path.is_dir() and path.name in CLUTTER_DIR_NAMES:
            clutter.append(relpath(path, repo_path) + "/")

    return CheckResult(
        tool_id="check_archive_layout",
        status="warning" if clutter else "pass",
        summary=(
            f"Found {len(clutter)} clutter item(s) in archive."
            if clutter
            else "Archive layout is clean (no obvious clutter detected)."
        ),
        evidence=[{"path": p, "kind": "clutter"} for p in clutter],
    )


def check_output_naming_convention(repo_path: Path, **_: object) -> CheckResult:
    """bj-04-results-linked: outputs use figure*/table* style names."""
    candidates: list[Path] = []
    for d in ("output", "outputs", "results", "figures", "tables", "."):
        p = repo_path / d
        if p.is_dir():
            for ext in (".pdf", ".png", ".jpg", ".csv", ".tex"):
                candidates.extend(p.glob(f"*{ext}"))

    figure_pattern = re.compile(r"^(figure|fig|table|tbl)[\s_\-]?\d+", re.IGNORECASE)
    matching = [c for c in candidates if figure_pattern.match(c.name)]

    return CheckResult(
        tool_id="check_output_naming_convention",
        status="pass" if matching else "warning",
        summary=(
            f"{len(matching)} output file(s) follow figure*/table* naming convention."
            if matching
            else "No output files following figure*/table* convention were detected "
                 "(may indicate outputs are generated at runtime and not committed)."
        ),
        evidence=[{"file": relpath(p, repo_path)} for p in matching[:20]],
        metadata={"n_matching": len(matching)},
    )
