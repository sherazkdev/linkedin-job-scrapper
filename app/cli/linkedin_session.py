"""Inspect or clear user-controlled LinkedIn Playwright session storage (never logs secrets)."""

import argparse
import logging
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.collection.linkedin.docker_session import copy_storage_to_docker_volume
from app.modules.collection.linkedin.host_login import (
    DEFAULT_HOST_STORAGE,
    resolve_host_output_path,
    run_interactive_login,
)
from app.modules.collection.linkedin.session import LinkedInSessionStore

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinkedIn session utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Show whether storage state exists")
    sub.add_parser("logout", help="Delete stored session state")
    sub.add_parser("prepare", help="Show manual authentication instructions")
    login = sub.add_parser("login", help="Host-only: open headed Chromium for manual sign-in")
    login.add_argument(
        "--output",
        default=None,
        help=f"Where to save storage state (default: {DEFAULT_HOST_STORAGE})",
    )
    install = sub.add_parser(
        "install-docker",
        help="Copy host storage_state.json into global_jobs_linkedin_auth volume",
    )
    install.add_argument(
        "--from",
        dest="from_path",
        default=None,
        metavar="PATH",
        help=f"Local session file (default: {DEFAULT_HOST_STORAGE})",
    )
    return parser.parse_args()


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    store = LinkedInSessionStore(settings.linkedin_storage_state_path)

    if args.command == "status":
        status = store.status()
        print(f"exists={status.exists} readable={status.readable} cookies={status.cookie_count}")
        print(status.message)
        raise SystemExit(0 if status.readable or not status.exists else 1)

    if args.command == "logout":
        removed = store.delete()
        print("Session cleared." if removed else "No session file to remove.")
        raise SystemExit(0)

    if args.command == "prepare":
        store.ensure_parent()
        host_default = resolve_host_output_path(None)
        print("Manual LinkedIn authentication (safe path):")
        print("1. On your Windows/Mac/Linux host (not Docker), create a venv and install:")
        print("     pip install -r requirements-collector.txt")
        print("     playwright install chromium")
        print("2. Run interactive login (headed browser):")
        print("     python -m app.cli.linkedin_session login")
        print(f"   Session is saved to: {host_default} (gitignored)")
        print("3. Copy into Docker volume:")
        print("     python -m app.cli.linkedin_session install-docker")
        print("4. Verify inside collector:")
        print(
            "     docker compose --profile collector run --rm collector "
            "python -m app.cli.linkedin_session status"
        )
        print()
        print(
            "The `prepare` command shows instructions only. Use `login` for the browser window."
        )
        raise SystemExit(0)

    if args.command == "login":
        out = resolve_host_output_path(args.output)
        run_interactive_login(out)
        print(f"Session saved (path only): {out}")
        print("Next: python -m app.cli.linkedin_session install-docker")
        raise SystemExit(0)

    if args.command == "install-docker":
        local = Path(args.from_path) if args.from_path else resolve_host_output_path(None)
        copy_storage_to_docker_volume(local)
        print(f"Session installed to Docker volume from: {local}")
        raise SystemExit(0)

    raise SystemExit(2)


if __name__ == "__main__":
    main()
