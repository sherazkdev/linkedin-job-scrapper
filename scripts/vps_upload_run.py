"""Upload and run a local shell script on the VPS (no secrets in repo)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from vps_remote import _connect


def _stream_remote_command(
    client: paramiko.SSHClient,
    remote_cmd: str,
    *,
    wall_timeout_s: int,
) -> int:
    """Run remote command with wall-clock timeout and live stdout/stderr streaming."""
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport not available")

    channel = transport.open_session()
    channel.settimeout(1.0)
    channel.exec_command(remote_cmd)
    deadline = time.monotonic() + wall_timeout_s
    stdout_buf = bytearray()
    stderr_buf = bytearray()

    while True:
        if channel.exit_status_ready():
            break
        if time.monotonic() > deadline:
            sys.stderr.write(
                f"\n[vps_upload_run] Wall-clock timeout ({wall_timeout_s}s) — closing SSH channel\n"
            )
            try:
                channel.close()
            except Exception:
                pass
            raise TimeoutError(f"Remote command exceeded {wall_timeout_s}s wall-clock limit")

        if channel.recv_ready():
            chunk = channel.recv(4096)
            if chunk:
                stdout_buf.extend(chunk)
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        if channel.recv_stderr_ready():
            chunk = channel.recv_stderr(4096)
            if chunk:
                stderr_buf.extend(chunk)
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
        time.sleep(0.2)

    while channel.recv_ready():
        chunk = channel.recv(4096)
        if chunk:
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    while channel.recv_stderr_ready():
        chunk = channel.recv_stderr(4096)
        if chunk:
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()

    return channel.recv_exit_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Wall-clock limit for the remote script (seconds)",
    )
    args = parser.parse_args()
    client = _connect()
    remote_path = f"/tmp/{args.script.name}"
    script_bytes = args.script.read_bytes()
    try:
        sys.stderr.write(f"[vps_upload_run] Uploading {args.script.name} -> {remote_path}\n")
        import base64

        b64 = base64.b64encode(script_bytes).decode("ascii")
        install_cmd = (
            f"printf '%s' '{b64}' | base64 -d > {remote_path} && chmod 700 {remote_path}"
        )
        _stdin, _stdout, _stderr = client.exec_command(install_cmd, timeout=120)
        err = _stderr.read().decode("utf-8", errors="replace")
        code = _stdout.channel.recv_exit_status()
        if code != 0:
            sys.stderr.write(f"[vps_upload_run] base64 install failed code={code} err={err[:200]}\n")
            raise RuntimeError(f"Remote script install failed with code {code}")
        remote_cmd = f"bash -euo pipefail {remote_path}"
        sys.stderr.write(
            f"[vps_upload_run] Executing remote script (wall_timeout={args.timeout}s)\n"
        )
        try:
            code = _stream_remote_command(
                client, remote_cmd, wall_timeout_s=args.timeout
            )
        except TimeoutError:
            sys.stderr.write(
                "[vps_upload_run] Remote script timed out. "
                "Run scripts/server_pilot_reconcile.sh on the VPS if a pilot was in progress.\n"
            )
            raise SystemExit(124) from None
        raise SystemExit(code)
    finally:
        client.close()


if __name__ == "__main__":
    os.environ.setdefault(
        "DEPLOY_SSH_CREDS_FILE",
        str(
            Path(
                r"C:\Users\shera\AppData\Local\Cursor\AgentStores\cursor_agent_stores\u511394734\files\deploy_ssh_creds.local"
            )
        ),
    )
    main()