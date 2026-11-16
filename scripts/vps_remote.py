"""Run remote shell commands over SSH (key-first; password only via DEPLOY_SSH_PASS env)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import paramiko


def _load_connection_params() -> tuple[str, str, str | None, list[str]]:
    host = os.environ.get("DEPLOY_SSH_HOST", "13.140.131.209")
    user = os.environ.get("DEPLOY_SSH_USER", "root")
    password = os.environ.get("DEPLOY_SSH_PASS")

    creds_path = Path(
        os.environ.get(
            "DEPLOY_SSH_CREDS_FILE",
            Path.home() / ".cursor_deploy_ssh_creds",
        )
    )
    if creds_path.is_file():
        for line in creds_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            k = key.strip().upper()
            v = value.strip()
            if k == "HOST" and host == "13.140.131.209":
                host = v
            elif k == "USER" and user == "root":
                user = v
            elif k == "PASS" and password is None:
                password = v

    key_paths: list[str] = []
    key_env = os.environ.get("DEPLOY_SSH_KEY_PATH")
    if key_env:
        key_paths.append(key_env)
    ssh_dir = Path.home() / ".ssh"
    for name in ("id_ed25519", "id_rsa", "contabo_deploy"):
        candidate = ssh_dir / name
        if candidate.is_file():
            key_paths.append(str(candidate))

    if not key_paths and password is None:
        raise SystemExit(
            "SSH auth unavailable: set DEPLOY_SSH_PASS for this session, "
            "DEPLOY_SSH_KEY_PATH, or install a key in ~/.ssh/"
        )
    return host, user, password, key_paths


def _connect() -> paramiko.SSHClient:
    host, user, password, key_paths = _load_connection_params()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last_err: Exception | None = None
    for key_path in key_paths:
        try:
            pkey = paramiko.RSAKey.from_private_key_file(key_path)
        except Exception:
            try:
                pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
            except Exception as exc:
                last_err = exc
                continue
        try:
            client.connect(
                host,
                username=user,
                pkey=pkey,
                timeout=30,
                allow_agent=False,
                look_for_keys=False,
            )
            sys.stderr.write(f"[vps_remote] Connected with key file\n")
            return client
        except Exception as exc:
            last_err = exc
            client.close()
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        client.connect(
            host,
            username=user,
            password=password,
            timeout=30,
            allow_agent=True,
            look_for_keys=True,
        )
        sys.stderr.write("[vps_remote] Connected with password/agent\n")
        return client
    raise SystemExit(f"SSH connect failed: {last_err!s}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="uname -a")
    parser.add_argument("--host", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--stream", action="store_true", help="Stream stdout/stderr while running")
    args = parser.parse_args()

    client = _connect()
    try:
        _stdin, stdout, stderr = client.exec_command(args.command, timeout=args.timeout)
        if args.stream:
            deadline = time.monotonic() + args.timeout
            while not stdout.channel.exit_status_ready():
                if time.monotonic() > deadline:
                    stdout.channel.close()
                    raise TimeoutError(f"Command exceeded {args.timeout}s")
                if stdout.channel.recv_ready():
                    chunk = stdout.channel.recv(4096)
                    if chunk:
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                if stdout.channel.recv_stderr_ready():
                    chunk = stdout.channel.recv_stderr(4096)
                    if chunk:
                        sys.stderr.buffer.write(chunk)
                        sys.stderr.buffer.flush()
                time.sleep(0.15)
            while stdout.channel.recv_ready():
                sys.stdout.buffer.write(stdout.channel.recv(4096))
            while stdout.channel.recv_stderr_ready():
                sys.stderr.buffer.write(stdout.channel.recv_stderr(4096))
            code = stdout.channel.recv_exit_status()
        else:
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if out:
                sys.stdout.write(out)
            if err:
                sys.stderr.write(err)
            code = stdout.channel.recv_exit_status()
        raise SystemExit(code)
    finally:
        client.close()


if __name__ == "__main__":
    main()