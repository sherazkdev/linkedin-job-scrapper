"""Copy host storage state into the Docker linkedin_auth volume (no secret output)."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_VOLUME = "global_jobs_linkedin_auth"
CONTAINER_PATH = "/data/linkedin/storage_state.json"


def copy_storage_to_docker_volume(
    local_file: Path,
    *,
    volume_name: str = DEFAULT_VOLUME,
) -> None:
    if not local_file.is_file():
        raise SystemExit(f"Local session file not found: {local_file}")

    if not shutil.which("docker"):
        raise SystemExit("Docker CLI not found. Install Docker Desktop and retry.")

    local_abs = local_file.resolve()
    # One-shot Alpine container: bind-mount host file read-only, write into named volume.
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{volume_name}:/data/linkedin",
        "-v",
        f"{local_abs}:{CONTAINER_PATH}.host:ro",
        "alpine:3.20",
        "sh",
        "-c",
        (
            f"cp {CONTAINER_PATH}.host {CONTAINER_PATH} "
            f"&& chown 1000:1000 {CONTAINER_PATH} "
            f"&& chmod 600 {CONTAINER_PATH}"
        ),
    ]
    logger.info("Installing session into Docker volume %s", volume_name)
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to copy session into volume {volume_name} "
            f"(exit {result.returncode}). Check Docker is running."
        )