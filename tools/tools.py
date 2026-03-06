"""
tools.py

Central registry of tools available to AI agents.
Each tool wraps a deterministic function implemented in separate modules.
"""

from kbe_agent.pdf2text import pdf2text
from kbe_agent.clean_pdf_text import clean_pdf_text

from cqv_agent.extract_zip import extract_zip
from cqv_agent.list_files import list_files
from cqv_agent.read_file import read_file

from er_agent.create_file import create_file
from er_agent.launch_env import launch_env


TOOLS = {
    "extract_zip": {
        "function": extract_zip,
        "description": "Extract a zip archive in place.",
        "args": {
            "zip_path": "Path to zip archive"
        }
    },

    "list_files": {
        "function": list_files,
        "description": "List all files in a directory recursively.",
        "args": {
            "directory": "Directory to explore"
        }
    },

    "read_file": {
        "function": read_file,
        "description": "Read a file and return its content.",
        "args": {
            "filepath": "Path to the file"
        }
    },

    "create_file": {
        "function": create_file,
        "description": "Create a file with given text content.",
        "args": {
            "filename": "Name/path of file",
            "text": "Content to write"
        }
    },

    "pdf2text": {
        "function": pdf2text,
        "description": "Extract raw text from a PDF file.",
        "args": {
            "pdf_path": "Path to PDF"
        }
    },

    "clean_pdf_text": {
        "function": clean_pdf_text,
        "description": "Clean PDF-extracted text by removing LaTeX artifacts and noise.",
        "args": {
            "raw_text": "Raw text extracted from a PDF"
        }
    },

    "launch_env": {
        "function": launch_env,
        "description": "Launch a Docker environment to run a reproducibility experiment.",
        "args": {
            "engine": "Runtime engine (python or r)",
            "version": "Engine version",
            "dependencies": "List of (package, version)",
            "dependency_path" : "path to environment loading (renv, requirements)."
            "code_path": "Path to experiment code",
            "data_path": "Optional dataset path"
        }
    }
}


def get_tool(name: str):
    """
    Retrieve a tool function by name.
    """
    if name not in TOOLS:
        raise ValueError(f"Tool '{name}' not found")

    return TOOLS[name]["function"]


def list_tools():
    """
    Return available tools with descriptions.
    """
    return {
        name: {
            "description": tool["description"],
            "args": tool["args"]
        }
        for name, tool in TOOLS.items()
    }


def run_tool(name: str, **kwargs):
    """
    Execute a tool by name with provided arguments.
    """
    tool = get_tool(name)
    return tool(**kwargs)