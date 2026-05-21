"""
tools.py

Central registry of tools available to AI agents.
Each tool wraps a deterministic function implemented in separate modules.
"""

import importlib.util
import sys
import os


# Load KBE agent modules
spec = importlib.util.spec_from_file_location("kbe_agent.pdf2text", "tools/kbe_agent/pdf2text.py")
pdf2text_module = importlib.util.module_from_spec(spec)
sys.modules["kbe_agent.pdf2text"] = pdf2text_module
spec.loader.exec_module(pdf2text_module)
pdf2text = pdf2text_module.pdf2text

spec = importlib.util.spec_from_file_location("kbe_agent.clean_pdf_text", "tools/kbe_agent/clean_pdf_text.py")
clean_pdf_text_module = importlib.util.module_from_spec(spec)
sys.modules["kbe_agent.clean_pdf_text"] = clean_pdf_text_module
spec.loader.exec_module(clean_pdf_text_module)
clean_pdf_text = clean_pdf_text_module.clean_pdf_text


# Load CQV agent modules
spec = importlib.util.spec_from_file_location("cqv_agent.extract_zip", "tools/cqv_agent/extract_zip.py")
extract_zip_module = importlib.util.module_from_spec(spec)
sys.modules["cqv_agent.extract_zip"] = extract_zip_module
spec.loader.exec_module(extract_zip_module)
extract_zip = extract_zip_module.extract_zip

spec = importlib.util.spec_from_file_location("cqv_agent.list_files", "tools/cqv_agent/list_files.py")
list_files_module = importlib.util.module_from_spec(spec)
sys.modules["cqv_agent.list_files"] = list_files_module
spec.loader.exec_module(list_files_module)
list_files = list_files_module.list_files

spec = importlib.util.spec_from_file_location("cqv_agent.read_file", "tools/cqv_agent/read_file.py")
read_file_module = importlib.util.module_from_spec(spec)
sys.modules["cqv_agent.read_file"] = read_file_module
spec.loader.exec_module(read_file_module)
read_file = read_file_module.read_file

# Import get-dependencies module (file with hyphen in name)
spec = importlib.util.spec_from_file_location("cqv_agent.get_dependencies", "tools/cqv_agent/get-dependencies.py")
get_dependencies_module = importlib.util.module_from_spec(spec)
sys.modules["cqv_agent.get_dependencies"] = get_dependencies_module
spec.loader.exec_module(get_dependencies_module)
get_dependencies = get_dependencies_module.get_dependencies


# Load ER agent modules
spec = importlib.util.spec_from_file_location("er_agent.create_file", "tools/er_agent/create_file.py")
create_file_module = importlib.util.module_from_spec(spec)
sys.modules["er_agent.create_file"] = create_file_module
spec.loader.exec_module(create_file_module)
create_file = create_file_module.create_file

spec = importlib.util.spec_from_file_location("er_agent.launch_env", "tools/er_agent/launch_env.py")
launch_env_module = importlib.util.module_from_spec(spec)
sys.modules["er_agent.launch_env"] = launch_env_module
spec.loader.exec_module(launch_env_module)
launch_env = launch_env_module.launch_env

# Import evaluate-results module (file with hyphen in name)
spec = importlib.util.spec_from_file_location("er_agent.evaluate_results", "tools/er_agent/evaluate-results.py")
evaluate_results_module = importlib.util.module_from_spec(spec)
sys.modules["er_agent.evaluate_results"] = evaluate_results_module
spec.loader.exec_module(evaluate_results_module)
evaluate_results = evaluate_results_module.evaluate_results


# Wrapper functions to handle dict responses
def pdf2text_wrapper(pdf_path: str) -> str:
    """Wrapper to extract text from pdf2text dict response."""
    result = pdf2text(pdf_path)
    if result.get("success"):
        return result["text"]
    raise RuntimeError(f"pdf2text failed: {result.get('error')}")


def clean_pdf_text_wrapper(raw_text: str) -> str:
    """Wrapper to extract cleaned text from clean_pdf_text dict response."""
    result = clean_pdf_text(raw_text)
    if result.get("success"):
        return result["cleaned_text"]
    raise RuntimeError(f"clean_pdf_text failed: {result.get('error')}")



# Tool registry
TOOLS = {
    "extract_zip": {
        "function": extract_zip,
        "description": "Extract a zip archive in place.",
        "args": {
            "zip_filepath": "Path to zip archive"
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
        "function": pdf2text_wrapper,
        "description": "Extract raw text from a PDF file.",
        "args": {
            "pdf_path": "Path to PDF"
        }
    },

    "clean_pdf_text": {
        "function": clean_pdf_text_wrapper,
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
            "dependency_path": "path to environment loading (renv, requirements).",
            "code_path": "Path to experiment code",
            "data_path": "Optional dataset path"
        }
    },

    "get_dependencies": {
        "function": get_dependencies,
        "description": "Extract dependencies from a code repository (Python, R, system, Docker).",
        "args": {
            "repo_path": "Path to the code repository"
        }
    },

    "evaluate_results": {
        "function": evaluate_results,
        "description": "Evaluate experimental results against paper claims and check for reproducibility.",
        "args": {
            "results_path": "Path to experimental results directory",
            "paper_claims": "Dictionary of claims reported in the paper"
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
