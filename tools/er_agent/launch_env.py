import subprocess
from pathlib import Path
from typing import List, Tuple


SUPPORTED_ENGINES = {
    ("python", "3.11"): "python:3.11",
    ("r", "4.4"): "rocker/r-ver:4.4.0"
}

def launch_env(
    engine: str,
    version: str,
    dependencies: List[Tuple[str, str]],
    dependency_path: str,
    code_path: str,
    data_path: str = ""
) -> dict:
    """
    Launch a reproducible Docker environment for running a scientific experiment.

    Args:
        engine (str): Runtime engine ("python" or "r").
        version (str): Engine version (supported: python 3.11, r 4.4).
        dependencies (List[Tuple[str, str]]): List of (package, version).
        dependeny_path: (str) path to environment loading (renv, requirements). 
        code_path (str): Path to load code.
        data_path (str): Optional path to dataset.

    Returns:
        dict containing:
            success (bool)
            container_id (str | None)
            error (str | None)
    """

    try:

        if (engine, version) not in SUPPORTED_ENGINES:
            return {
                "success": False,
                "container_id": None,
                "error": f"Unsupported engine/version: {engine} {version}"
            }

        image = SUPPORTED_ENGINES[(engine, version)]

        code = Path(code_path).resolve()
        data = Path(data_path).resolve() if data_path else None
        experiment_dir = Path("experiment-run").resolve()

        if not experiment_dir.exists():
            return {
                "success": False,
                "container_id": None,
                "error": "experiment-run directory missing. Cannot launch experiment."
            }

        # Build dependency install command
        install_cmd = ""

        if dependencies:

            if engine == "python":
                pkgs = " ".join(
                    f"{p}=={v}" if v else p for p, v in dependencies
                )
                install_cmd = f"pip install {pkgs} && "

            if engine == "r":
                pkgs = ",".join(
                    f'"{p}"' for p, _ in dependencies
                )
                install_cmd = (
                    f'R -e \'install.packages(c({pkgs}), repos="https://cloud.r-project.org")\' && '
                )

        install_cmd += build_install_command(engine, code_path)

        run_command = install_cmd + "bash"

        docker_cmd = [
            "docker", "run", "-dit", "--rm",  # remove when stopped
            "-v", f"{code}:/workspace/code:rw",
            "-v", f"{experiment_dir}:/workspace/experiment-run:rw",
        ]

        if data:
            docker_cmd += ["-v", f"{data}:/workspace/data:rw"]

        docker_cmd += [
            image,
            "bash",
            "-c",
            run_command
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "success": False,
                "container_id": None,
                "error": result.stderr
            }

        container_id = result.stdout.strip()

        return {
            "success": True,
            "container_id": container_id,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "container_id": None,
            "error": str(e)
        }


def build_install_command(engine: str, dependency_path: str) -> str:
    """
    Build the dependency installation command executed inside the Docker container.

    Args:
        engine (str): "python" or "r"
        dependency_path (str): Path to dependency file or project directory.

    Returns:
        str: Shell command used to install dependencies.
    """

    dep = Path(dependency_path)

    if engine == "python":

        requirements = dep if dep.name == "requirements.txt" else dep / "requirements.txt"

        if requirements.exists():
            return f"pip install --no-cache-dir -r {requirements} && "

        return ""

    if engine == "r":

        renv_lock = dep / "renv.lock"

        if renv_lock.exists():
            return (
                "R -e 'install.packages(\"renv\", repos=\"https://cloud.r-project.org\");"
                "renv::restore()' && "
            )

        return ""

    return ""