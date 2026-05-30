"""
Dangerous-pattern checks: rm(list=ls()), install.packages, eval/parse,
system calls, hardcoded secrets, attach(), downloads, unsafe deserialization.

Each check scans source files line-by-line, strips trailing comments, and
records every match with file:line. Severity comes from the YAML, not here.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import CheckResult, iter_source_files, relpath, strip_inline_comment


def _scan(
    repo_path: Path,
    tool_id: str,
    patterns: list[tuple[re.Pattern, str]],
    languages: set[str],
    summary_noun: str,
    *,
    status_when_found: str = "fail",
) -> CheckResult:
    """Common line-scanning skeleton used by all danger-pattern checks."""
    offenders: list[dict] = []
    for path, lang in iter_source_files(repo_path, languages=languages):
        for i, raw in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            code = strip_inline_comment(raw)
            if not code.strip():
                continue
            for pat, label in patterns:
                if pat.search(code):
                    offenders.append({
                        "file": relpath(path, repo_path),
                        "line": i,
                        "snippet": raw.strip()[:200],
                        "language": lang,
                        "pattern": label,
                    })
                    break

    return CheckResult(
        tool_id=tool_id,
        status=status_when_found if offenders else "pass",
        summary=(
            f"Found {len(offenders)} occurrence(s) of {summary_noun}."
            if offenders
            else f"No occurrences of {summary_noun} detected."
        ),
        evidence=offenders[:50],
        metadata={"total_violations": len(offenders)},
    )


# ---------------------------------------------------------------------------
# Workspace clearing (R)
# ---------------------------------------------------------------------------

WORKSPACE_CLEAR_PATTERNS = [
    (re.compile(r"\brm\s*\(\s*list\s*=\s*ls\s*\("), "rm(list=ls())"),
    (re.compile(r"\bremove\s*\(\s*list\s*=\s*ls\s*\("), "remove(list=ls())"),
]


def check_no_workspace_clear(repo_path: Path, **_: object) -> CheckResult:
    """audit-qual-no-workspace-clear: no rm(list=ls()) in R code."""
    return _scan(
        repo_path,
        tool_id="check_no_workspace_clear",
        patterns=WORKSPACE_CLEAR_PATTERNS,
        languages={"r"},
        summary_noun="workspace-clearing calls",
        status_when_found="warning",
    )


# ---------------------------------------------------------------------------
# Auto-install (R + Python)
# ---------------------------------------------------------------------------

AUTO_INSTALL_PATTERNS = [
    (re.compile(r"\binstall\.packages\s*\("),       "install.packages()"),
    (re.compile(r"\bdevtools::install_\w+\s*\("),   "devtools::install_*()"),
    (re.compile(r"\bremotes::install_\w+\s*\("),    "remotes::install_*()"),
    (re.compile(r"\bBiocManager::install\s*\("),    "BiocManager::install()"),
    (re.compile(r"\bpip\.main\s*\("),               "pip.main()"),
    (re.compile(r"!\s*pip\s+install\b"),            "!pip install (notebook magic)"),
    (re.compile(r"subprocess\..*['\"]\s*pip\s+install"), "subprocess pip install"),
]


def check_no_auto_install(repo_path: Path, **_: object) -> CheckResult:
    """audit-qual-no-auto-install: no silent auto-install of dependencies."""
    return _scan(
        repo_path,
        tool_id="check_no_auto_install",
        patterns=AUTO_INSTALL_PATTERNS,
        languages={"r", "python"},
        summary_noun="automatic package-installation calls",
    )


# ---------------------------------------------------------------------------
# Eval / parse
# ---------------------------------------------------------------------------

EVAL_PATTERNS = [
    (re.compile(r"\beval\s*\("),               "eval()"),
    (re.compile(r"\bexec\s*\("),               "exec() (Python)"),
    (re.compile(r"\bparse\s*\(\s*text\s*="),   "parse(text=...) (R)"),
    (re.compile(r"\bstr2lang\s*\("),           "str2lang() (R)"),
    (re.compile(r"\bbase::eval\s*\("),         "base::eval() (R)"),
]


def check_no_eval_parse(repo_path: Path, **_: object) -> CheckResult:
    """cqv-sec-no-eval: no dynamic-code execution on strings."""
    return _scan(
        repo_path,
        tool_id="check_no_eval_parse",
        patterns=EVAL_PATTERNS,
        languages={"r", "python"},
        summary_noun="dynamic-code-execution calls",
    )


# ---------------------------------------------------------------------------
# System / shell calls
# ---------------------------------------------------------------------------

SYSTEM_CALL_PATTERNS = [
    (re.compile(r"\bos\.system\s*\("),                            "os.system()"),
    (re.compile(r"\bsubprocess\.\w+\s*\([^)]*shell\s*=\s*True"),  "subprocess(..., shell=True)"),
    (re.compile(r"\bos\.popen\s*\("),                             "os.popen()"),
    (re.compile(r"\bsystem\s*\(.*[\"']"),                          "system() with string literal (R)"),
    (re.compile(r"\bsystem2\s*\("),                               "system2() (R)"),
    (re.compile(r"\bshell\s*\("),                                 "shell() (R)"),
]


def check_no_system_calls(repo_path: Path, **_: object) -> CheckResult:
    """cqv-sec-no-system-calls: no shell-command execution with literal/interpolated strings."""
    return _scan(
        repo_path,
        tool_id="check_no_system_calls",
        patterns=SYSTEM_CALL_PATTERNS,
        languages={"r", "python"},
        summary_noun="shell-command execution calls",
    )


# ---------------------------------------------------------------------------
# Hardcoded secrets
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    (re.compile(r"""(?i)\b(api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token)\s*[:=]\s*['"][^'"]{12,}['"]"""),
     "key-name assignment to long string"),
    (re.compile(r"""(?i)\b(password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]"""),
     "password assignment"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"),    "AWS access key id"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),  "OpenAI/Anthropic-style key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "GitHub personal access token"),
    (re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
     "PEM private key"),
]


def check_no_hardcoded_secrets(repo_path: Path, **_: object) -> CheckResult:
    """cqv-sec-no-hardcoded-secrets: regex sweep for common secret patterns."""
    return _scan(
        repo_path,
        tool_id="check_no_hardcoded_secrets",
        patterns=SECRET_PATTERNS,
        languages={"r", "python"},
        summary_noun="possible hardcoded secrets",
    )


# ---------------------------------------------------------------------------
# attach() (R)
# ---------------------------------------------------------------------------

ATTACH_PATTERNS = [
    (re.compile(r"\battach\s*\("), "attach()"),
]


def check_no_attach(repo_path: Path, **_: object) -> CheckResult:
    """cqv-data-no-attach: no R attach() calls."""
    return _scan(
        repo_path,
        tool_id="check_no_attach",
        patterns=ATTACH_PATTERNS,
        languages={"r"},
        summary_noun="R attach() calls",
    )


# ---------------------------------------------------------------------------
# Arbitrary network downloads
# ---------------------------------------------------------------------------

DOWNLOAD_PATTERNS = [
    (re.compile(r"\bdownload\.file\s*\("),       "download.file() (R)"),
    (re.compile(r"\bcurl::curl_download\s*\("),  "curl::curl_download() (R)"),
    (re.compile(r"\burllib\.request\.urlopen"),  "urllib urlopen (Python)"),
    (re.compile(r"\bwget\.download\s*\("),       "wget.download() (Python)"),
    (re.compile(r"\brequests\.(get|post)\s*\("), "requests.get/post() (Python)"),
]


def check_no_arbitrary_downloads(repo_path: Path, **_: object) -> CheckResult:
    """cqv-sec-no-arbitrary-downloads: report any runtime network fetches."""
    return _scan(
        repo_path,
        tool_id="check_no_arbitrary_downloads",
        patterns=DOWNLOAD_PATTERNS,
        languages={"r", "python"},
        summary_noun="runtime network fetches",
        status_when_found="warning",
    )


# ---------------------------------------------------------------------------
# Unsafe deserialization
# ---------------------------------------------------------------------------

UNSAFE_DESER_PATTERNS = [
    (re.compile(r"\breadRDS\s*\("),           "readRDS() (R)"),
    (re.compile(r"\bload\s*\("),              "load() (R)"),
    (re.compile(r"\bunserialize\s*\("),       "unserialize() (R)"),
    (re.compile(r"\bpickle\.loads?\s*\("),    "pickle.load/loads (Python)"),
    (re.compile(r"\bjoblib\.load\s*\("),      "joblib.load (Python)"),
    (re.compile(r"\byaml\.load\s*\("),        "yaml.load (unsafe; use safe_load)"),
]


def check_no_unsafe_deserialization(repo_path: Path, **_: object) -> CheckResult:
    """cqv-sec-no-unsafe-deserialization: report deserialization of opaque objects."""
    return _scan(
        repo_path,
        tool_id="check_no_unsafe_deserialization",
        patterns=UNSAFE_DESER_PATTERNS,
        languages={"r", "python"},
        summary_noun="deserialization calls (review for trusted source)",
        status_when_found="warning",
    )
