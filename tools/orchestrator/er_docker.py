"""ER Docker execution seam (LOGIC.md §3.3).

The actual `docker run` lives behind a callable seam (``RunFn``) so the rest of
the ER stage — and its tests — never touch Docker. The default implementation
shells out to the docker CLI; tests inject a fake that returns canned results.

Container contract (what the default runner enforces):
  * image: ghcr.io/sistm/ai4reproducibility:r<version> (from execution_environment)
  * --network none AFTER renv::restore() — restore needs the network, the run
    does not. The default runner does restore + run in one container with the
    network on, because turning it off mid-container is not possible with a
    single `docker run`; the network-off guarantee is enforced by running the
    analysis step as a separate `docker run --network none` once restore has
    populated the renv cache on the mounted volume. See `run_in_container`.
  * --memory 4g, --rm, no privileged flags
  * a hard timeout (subprocess level) so a runaway run cannot hang the pipeline
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_IMAGE_PREFIX = "ghcr.io/sistm/ai4reproducibility:r"
DEFAULT_MEMORY = "4g"


@dataclass
class RunRequest:
    """A single container execution request."""

    image: str
    workspace: Path           # host path mounted at /workspace
    command: list[str]        # e.g. ["Rscript", "main.R"]
    timeout_seconds: int
    network: bool = False     # True only for the renv::restore() step
    memory: str = DEFAULT_MEMORY


@dataclass
class RunResult:
    """Outcome of a container execution."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    artifacts: list[str] = field(default_factory=list)  # files produced under workspace

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class RunFn(Protocol):
    """Seam: anything that turns a RunRequest into a RunResult."""

    def __call__(self, request: RunRequest) -> RunResult: ...


def image_for_r_version(r_version: str | None) -> str:
    """Map a declared R version to the GHCR image tag.

    Falls back to a default tag when the version is missing or unrecognised;
    the fat base image is forward-compatible enough that a minor mismatch is
    usually fine, and a mismatch is already surfaced as a finding upstream.
    """
    default = "4.4.2"
    version = (r_version or default).strip()
    # Normalise "R version 4.3.2 (2023-...)" style strings to "4.3.2".
    import re
    m = re.search(r"(\d+\.\d+\.\d+)", version)
    tag = m.group(1) if m else default
    return f"{DEFAULT_IMAGE_PREFIX}{tag}"


def _docker_available() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=10,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_image(image: str, *, pull: bool = True) -> bool:
    """Ensure ``image`` is present locally, pulling from GHCR if needed.

    Returns True if the image is available after the call. Never raises.
    """
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=30,
        )
        if inspect.returncode == 0:
            return True
        if not pull:
            return False
        pulled = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, timeout=600,
        )
        return pulled.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def default_run_fn(request: RunRequest) -> RunResult:
    """Real Docker runner. Shells out to the docker CLI.

    Network is off by default (``--network none``); only the restore step
    passes ``network=True``. A subprocess-level timeout guarantees the call
    returns even if the container hangs.
    """
    cmd = [
        "docker", "run", "--rm",
        "--memory", request.memory,
        "--volume", f"{request.workspace.resolve()}:/workspace",
        "--workdir", "/workspace",
    ]
    if not request.network:
        cmd += ["--network", "none"]
    cmd.append(request.image)
    cmd += request.command

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=request.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            returncode=124,
            stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            timed_out=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RunResult(returncode=125, stdout="", stderr=f"docker invocation failed: {exc}")

    return RunResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def restore_and_run(
    workspace: Path,
    image: str,
    entry_command: list[str],
    *,
    run_timeout: int,
    restore_timeout: int = 1800,
    run_fn: RunFn | None = None,
) -> tuple[RunResult, RunResult | None]:
    """Two-container sequence: renv::restore() (network on), then the entry run
    (network off).

    Returns (restore_result, run_result). ``run_result`` is None if restore
    failed (we don't run the analysis against an incomplete environment).
    """
    runner: RunFn = run_fn or default_run_fn

    restore = runner(RunRequest(
        image=image,
        workspace=workspace,
        command=["Rscript", "-e", "renv::restore(prompt = FALSE)"],
        timeout_seconds=restore_timeout,
        network=True,
    ))
    if not restore.ok:
        return restore, None

    run = runner(RunRequest(
        image=image,
        workspace=workspace,
        command=entry_command,
        timeout_seconds=run_timeout,
        network=False,
    ))
    return restore, run
