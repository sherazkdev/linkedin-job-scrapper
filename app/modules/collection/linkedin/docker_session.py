"""Copy host storage state into the Docker linkedin_auth volume (no secret output)."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from app.modules.collection.linkedin.session_validation import (
    OfflineSessionQuality,
    inspect_offline_storage_state,
    write_session_epoch_marker,
)

logger = logging.getLogger(__name__)

DEFAULT_VOLUME = os.environ.get("LINKEDIN_AUTH_VOLUME_NAME", "linkedin_scraper_linkedin_auth")
CONTAINER_PATH = "/data/linkedin/storage_state.json"
EPOCH_CONTAINER_PATH = "/data/linkedin/session_epoch_at.json"


def copy_storage_to_docker_volume(
    local_file: Path,
    *,
    volume_name: str | None = None,
) -> None:
    volume = volume_name or DEFAULT_VOLUME
    if not local_file.is_file():
        raise SystemExit(f"Local session file not found: {local_file}")

    report = inspect_offline_storage_state(local_file)
    if report.quality not in {
        OfflineSessionQuality.LIKELY_AUTHENTICATED,
        OfflineSessionQuality.UNLIKELY_AUTHENTICATED,
    }:
        raise SystemExit(
            f"Refusing to install session: offline quality={report.quality.value} — {report.message}"
        )

    if not shutil.which("docker"):
        raise SystemExit("Docker CLI not found. Install Docker Desktop and retry.")

    local_abs = local_file.resolve()
    epoch_local = local_abs.parent / "session_epoch_at.json"
    if not epoch_local.is_file():
        write_session_epoch_marker(local_abs.parent)

    backup_script = (
        f"if [ -f {CONTAINER_PATH} ]; then "
        f"cp {CONTAINER_PATH} {CONTAINER_PATH}.bak.$(date -u +%Y%m%dT%H%M%SZ); fi"
    )
    install_script = (
        f"{backup_script} && "
        f"cp {CONTAINER_PATH}.host {CONTAINER_PATH} && "
        f"chown 1000:1000 {CONTAINER_PATH} && chmod 600 {CONTAINER_PATH}"
    )
    if epoch_local.is_file():
        install_script += (
            f" && cp {EPOCH_CONTAINER_PATH}.host {EPOCH_CONTAINER_PATH} "
            f"&& chown 1000:1000 {EPOCH_CONTAINER_PATH} && chmod 600 {EPOCH_CONTAINER_PATH}"
        )

    volumes = [
        f"{volume}:/data/linkedin",
        f"{local_abs}:{CONTAINER_PATH}.host:ro",
    ]
    if epoch_local.is_file():
        volumes.append(f"{epoch_local}:{EPOCH_CONTAINER_PATH}.host:ro")

    cmd = ["docker", "run", "--rm"]
    for mount in volumes:
        cmd.extend(["-v", mount])
    cmd.extend(["alpine:3.20", "sh", "-c", install_script])
    logger.info("Installing session into Docker volume %s", volume)
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to copy session into volume {volume} "
            f"(exit {result.returncode}). Check Docker is running."
        )