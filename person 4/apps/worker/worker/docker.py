"""
Docker container execution module for CrowdGPU Worker.

Provides secure, isolated execution of containerized compute jobs via Docker Engine CLI.
Implements argument validation, container sandboxing, timeout enforcement, output
capture, and resource cleanup.
"""

import logging
import re
import shlex
import subprocess
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Strict regex for Docker image reference validation:
# [REGISTRY[:PORT]/][NAMESPACE/]REPOSITORY[:TAG|@sha256:DIGEST]
# Disallows leading flags (-), spaces, and shell metacharacters.
_DOCKER_IMAGE_PATTERN = re.compile(
    r"^(?:(?=[a-zA-Z0-9])[a-zA-Z0-9._-]+(?::[0-9]+)?/)?"
    r"(?:(?=[a-zA-Z0-9])[a-zA-Z0-9._-]+/)?"
    r"(?=[a-zA-Z0-9])[a-zA-Z0-9._-]+"
    r"(?::(?=[a-zA-Z0-9._-])[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})?$"
)


@dataclass(frozen=True)
class DockerExecutionResult:
    """Result of a Docker container execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        """True if the container exited with code 0 without timing out or errors."""
        return self.exit_code == 0 and not self.timed_out and self.error_message is None


def validate_docker_image(image: str) -> str:
    """
    Validate that the specified Docker image name conforms to safe image naming conventions.

    Rejects flags (e.g. --privileged), shell metacharacters, spaces, and empty strings.
    """
    if not image or not isinstance(image, str):
        raise ValueError("Docker image name must be a non-empty string.")

    image = image.strip()
    if len(image) > 255:
        raise ValueError(
            f"Docker image name exceeds maximum length of 255 characters ({len(image)})."
        )

    if image.startswith("-"):
        raise ValueError(f"Docker image name must not start with a hyphen/flag: '{image}'.")

    # Reject null bytes and control characters
    if any(ord(c) < 32 or ord(c) == 127 for c in image):
        raise ValueError("Docker image name contains invalid control characters.")

    if not _DOCKER_IMAGE_PATTERN.match(image):
        raise ValueError(
            f"Invalid Docker image reference: '{image}'. "
            "Must follow [registry/][namespace/]repo[:tag|@digest] format."
        )

    return image


def parse_and_validate_command(command: str) -> list[str]:
    """
    Safely parse and validate a command string into an argument list using shlex.

    Prevents shell concatenation vulnerabilities and validates non-emptiness.
    """
    if not command or not isinstance(command, str) or not command.strip():
        raise ValueError("Command must be a non-empty string.")

    if "\0" in command:
        raise ValueError("Command contains forbidden null bytes.")

    try:
        args = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError(f"Failed to parse command syntax: {exc}") from exc

    if not args:
        raise ValueError("Parsed command arguments list is empty.")

    return args


def build_docker_run_args(
    image: str,
    command_args: Sequence[str],
    container_name: str,
) -> list[str]:
    """
    Construct safe argument list for `docker run`.

    Security constraints:
    - Never passes --privileged or host volume mounts.
    - Applies --security-opt=no-new-privileges to prevent privilege escalation.
    - Names the container explicitly for deterministic tracking and cleanup.
    - Passes --rm for automatic container removal on termination.
    """
    validated_image = validate_docker_image(image)
    if not container_name or not isinstance(container_name, str):
        raise ValueError("Container name must be a non-empty string.")

    # Sanitize container name: only alphanumeric, underscores, hyphens, and dots allowed
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$", container_name):
        raise ValueError(f"Invalid container name format: '{container_name}'.")

    args: list[str] = [
        "docker",
        "run",
        "--name",
        container_name,
        "--rm",
        "--security-opt=no-new-privileges",
        validated_image,
    ]
    args.extend(command_args)
    return args


def cleanup_container(container_name: str, timeout: float = 10.0) -> None:
    """
    Forcibly stop and remove a Docker container if it exists.

    Safe to call multiple times (idempotent).
    """
    if not container_name:
        return
    try:
        logger.debug("Cleaning up container: %s", container_name)
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        logger.warning(
            "Docker CLI executable not found during cleanup of container %s", container_name
        )
    except subprocess.TimeoutExpired:
        logger.warning("Timeout expired while cleaning up container %s", container_name)
    except Exception as exc:
        logger.warning("Unexpected error during cleanup of container %s: %s", container_name, exc)


def execute_docker_job(
    image: str,
    command: str,
    container_name: str | None = None,
    timeout: float = 300.0,
) -> DockerExecutionResult:
    """
    Execute a compute job inside a real Docker container.

    Runs the container using the Docker CLI, captures exit code and stdout/stderr,
    enforces execution timeout, and guarantees container cleanup.

    Note: GPU runtime (--gpus) is not requested by default unless verified and configured.
    Execution runs in unprivileged CPU mode.
    """
    # Generate container name if not provided
    name = container_name or f"crowdgpu-job-{uuid.uuid4().hex[:12]}"

    # Validate image and command upfront
    try:
        val_image = validate_docker_image(image)
        cmd_args = parse_and_validate_command(command)
        docker_args = build_docker_run_args(val_image, cmd_args, name)
    except ValueError as val_err:
        logger.error("Validation error for job container %s: %s", name, val_err)
        return DockerExecutionResult(
            exit_code=-1,
            stdout="",
            stderr="",
            error_message=str(val_err),
        )

    # Clean up any pre-existing container with same name before starting
    cleanup_container(name, timeout=5.0)

    logger.info("Executing Docker container '%s' with image '%s'", name, val_image)
    try:
        proc = subprocess.run(
            docker_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return DockerExecutionResult(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(
            "Container %s timed out after %.1f seconds. Forcibly cleaning up...",
            name,
            timeout,
        )
        cleanup_container(name, timeout=10.0)
        out = (
            exc.stdout
            if isinstance(exc.stdout, str)
            else (exc.stdout.decode("utf-8", "replace") if exc.stdout else "")
        )
        err = (
            exc.stderr
            if isinstance(exc.stderr, str)
            else (exc.stderr.decode("utf-8", "replace") if exc.stderr else "")
        )
        return DockerExecutionResult(
            exit_code=-1,
            stdout=out,
            stderr=err,
            timed_out=True,
            error_message=f"Container execution timed out after {timeout:.1f} seconds.",
        )
    except FileNotFoundError:
        msg = "Docker CLI ('docker') was not found in PATH."
        logger.error(msg)
        return DockerExecutionResult(
            exit_code=-1,
            stdout="",
            stderr="",
            error_message=msg,
        )
    except Exception as exc:
        logger.exception("Unexpected error executing Docker container %s: %s", name, exc)
        cleanup_container(name, timeout=10.0)
        return DockerExecutionResult(
            exit_code=-1,
            stdout="",
            stderr="",
            error_message=str(exc),
        )
    finally:
        # Guarantee container cleanup
        cleanup_container(name, timeout=10.0)
