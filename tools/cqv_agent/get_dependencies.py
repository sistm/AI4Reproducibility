"""
CQV Agent - Get Dependencies Module

This module extracts and validates dependency information from code repositories.
"""

from typing import Dict, List, Optional
import json
from pathlib import Path


class DependencyExtractor:
    """Extracts dependencies from various package managers and environment files."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.dependencies = {
            'python': [],
            'r': [],
            'system': [],
            'docker': None,
            'renv': None
        }
    
    def extract_python_dependencies(self) -> List[Dict[str, str]]:
        """Extract Python dependencies from requirements.txt or pyproject.toml."""
        deps = []
        
        # Check for requirements.txt
        req_file = self.repo_path / "requirements.txt"
        if req_file.exists():
            with open(req_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        deps.append({'package': line.split('==')[0], 'version': line.split('==')[1] if '==' in line else None})
        
        return deps
    
    def extract_r_dependencies(self) -> List[Dict[str, str]]:
        """Extract R dependencies from renv.lock or DESCRIPTION file."""
        deps = []
        
        # Check for renv.lock
        renv_file = self.repo_path / "renv.lock"
        if renv_file.exists():
            try:
                with open(renv_file, 'r') as f:
                    renv_data = json.load(f)
                    if 'Packages' in renv_data:
                        for pkg_name, pkg_data in renv_data['Packages'].items():
                            deps.append({
                                'package': pkg_name,
                                'version': pkg_data.get('Version')
                            })
            except Exception:
                pass
        
        return deps
    
    def extract_docker_dependencies(self) -> Optional[str]:
        """Check for Dockerfile and extract base image."""
        dockerfile = self.repo_path / "Dockerfile"
        if dockerfile.exists():
            with open(dockerfile, 'r') as f:
                for line in f:
                    if line.startswith('FROM'):
                        return line.strip()
        return None
    
    def extract_system_dependencies(self) -> List[str]:
        """Extract system-level dependencies from apt.txt or system-requirements.txt."""
        deps = []
        
        apt_file = self.repo_path / "apt.txt"
        if apt_file.exists():
            with open(apt_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        deps.append(line)
        
        return deps
    
    def extract_all(self) -> Dict[str, any]:
        """Extract all dependencies from the repository."""
        self.dependencies['python'] = self.extract_python_dependencies()
        self.dependencies['r'] = self.extract_r_dependencies()
        self.dependencies['system'] = self.extract_system_dependencies()
        self.dependencies['docker'] = self.extract_docker_dependencies()
        
        return self.dependencies


def get_dependencies(repo_path: str) -> Dict[str, any]:
    """
    Main function to extract dependencies from a repository.
    
    Args:
        repo_path: Path to the code repository
        
    Returns:
        Dictionary containing extracted dependencies by type
    """
    extractor = DependencyExtractor(repo_path)
    return extractor.extract_all()
