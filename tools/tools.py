"""
tools.py

Central registry of tools available to AI agents.
Each tool wraps a deterministic function implemented in a sibling subpackage.

Importable from any working directory once the project is installed
(`pip install -e .`) or when the repository root is on ``sys.path``.
"""

from collections.abc import Callable
from typing import Any

from tools.cqv_agent.extract_zip import extract_zip
from tools.cqv_agent.get_dependencies import get_dependencies
from tools.cqv_agent.list_files import list_files
from tools.cqv_agent.read_file import read_file
from tools.er_agent.create_file import create_file
from tools.er_agent.evaluate_results import evaluate_results
from tools.er_agent.launch_env import launch_env
from tools.kbe_agent.clean_pdf_text import clean_pdf_text as _clean_pdf_text_raw

# Standard package-relative imports. These work because every subfolder of
# ``tools/`` contains an empty ``__init__.py`` and the hyphenated module
# filenames have been renamed to use underscores.
from tools.kbe_agent.pdf2text import pdf2text as _pdf2text_raw

# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------
# The two PDF tools return ``{"success": bool, ...}`` dicts. The pipeline
# script (``assets/execute_workflow.sh``) treats their return values as
# plain strings, so we keep a thin wrapper that unpacks the dict and raises
# on failure. All other tools already return structured dicts that callers
# inspect directly.

def pdf2text(pdf_path: str) -> str:
    """Extract raw text from a PDF, raising on failure."""
    result = _pdf2text_raw(pdf_path)
    if result.get("success"):
        return result["text"]
    raise RuntimeError(f"pdf2text failed: {result.get('error')}")


def clean_pdf_text(raw_text: str) -> str:
    """Clean PDF-extracted text, raising on failure."""
    result = _clean_pdf_text_raw(raw_text)
    if result.get("success"):
        return result["cleaned_text"]
    raise RuntimeError(f"clean_pdf_text failed: {result.get('error')}")


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS: dict[str, dict[str, Any]] = {
    "extract_zip": {
        "function": extract_zip,
        "description": "Extract a zip archive in place.",
        "args": {"zip_filepath": "Path to zip archive"},
    },
    "list_files": {
        "function": list_files,
        "description": "List all files in a directory recursively.",
        "args": {"directory": "Directory to explore"},
    },
    "read_file": {
        "function": read_file,
        "description": "Read a file and return its content.",
        "args": {"filepath": "Path to the file"},
    },
    "create_file": {
        "function": create_file,
        "description": "Create a file with given text content.",
        "args": {
            "filename": "Name/path of file",
            "text": "Content to write",
        },
    },
    "pdf2text": {
        "function": pdf2text,
        "description": "Extract raw text from a PDF file.",
        "args": {"pdf_path": "Path to PDF"},
    },
    "clean_pdf_text": {
        "function": clean_pdf_text,
        "description": "Clean PDF-extracted text by removing LaTeX artifacts and noise.",
        "args": {"raw_text": "Raw text extracted from a PDF"},
    },
    "launch_env": {
        "function": launch_env,
        "description": "Launch a Docker environment to run a reproducibility experiment.",
        "args": {
            "engine": "Runtime engine (python or r)",
            "version": "Engine version",
            "dependencies": "List of (package, version)",
            "dependency_path": "Path to environment lockfile (renv.lock, requirements.txt).",
            "code_path": "Path to experiment code",
            "data_path": "Optional dataset path",
        },
    },
    "get_dependencies": {
        "function": get_dependencies,
        "description": "Extract dependencies from a code repository (Python, R, system, Docker).",
        "args": {"repo_path": "Path to the code repository"},
    },
    "evaluate_results": {
        "function": evaluate_results,
        "description": "Evaluate experimental results against paper claims and check for reproducibility.",
        "args": {
            "results_path": "Path to experimental results directory",
            "paper_claims": "Dictionary of claims reported in the paper",
        },
    },
}


def get_tool(name: str) -> Callable[..., Any]:
    """Retrieve a tool function by name."""
    if name not in TOOLS:
        raise ValueError(f"Tool '{name}' not found")
    return TOOLS[name]["function"]


def list_tools() -> dict[str, dict[str, Any]]:
    """Return available tools with descriptions."""
    return {
        name: {"description": tool["description"], "args": tool["args"]}
        for name, tool in TOOLS.items()
    }


def run_tool(name: str, **kwargs: Any) -> Any:
    """Execute a tool by name with provided arguments."""
    return get_tool(name)(**kwargs)
