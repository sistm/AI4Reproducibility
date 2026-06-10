"""
Static checks for the CQV agent.

Public surface: ``run_static_check(tool_id, repo_path, **kwargs)``.
"""

from .dispatch import (
    APPLICABLE_TO,
    REGISTRY,
    get_applicable_checks,
    list_static_checks,
    run_static_check,
)

__all__ = [
    "APPLICABLE_TO",
    "REGISTRY",
    "get_applicable_checks",
    "list_static_checks",
    "run_static_check",
]
