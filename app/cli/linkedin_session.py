"""Inspect or clear user-controlled LinkedIn Playwright session storage (never logs secrets)."""

import argparse
import json
import logging
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.collection.linkedin.docker_session import (
    DEFAULT_VOLUME,
    copy_storage_to_docker_volume,
)
from app.modules.collection.linkedin.host_login import (
    DEFAULT_HOST_STORAGE,
    LoginOutcome,
    resolve_host_output_path,
    run_interactive_login,
)
from app.modules.collection.linkedin.session import LinkedInSessionStore
from app.modules.collection.linkedin.session_validation import (
    LoginOutcome as VerifyOutcome,
    verify_online_feed_access,
)

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinkedIn session utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Offline storage state diagnostics")
    status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    status.add_argument(
        "--verify-online",
        action="store_true",
        help="One live feed request (requires --confirm-live-network)",
    )
    status.add_argument(
        "--confirm-live-network",
        action="store_true",
        help="Explicit consent for a single live LinkedIn request during status",
    )
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
        help=f"Copy host storage state into Docker volume ({DEFAULT_VOLUME})",
    )
    install.add_argument(
        "--from",
        dest="from_path",
        default=None,
        metavar="PATH",
        help=f"Local session file (default: {DEFAULT_HOST_STORAGE})",
    )
    install.add_argument(
        "--volume",
        default=None,
        help=f"Docker volume name (default: {DEFAULT_VOLUME})",
    )
    return parser.parse_args()


def _print_status(status, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(status.to_dict(), indent=2))
        return
    print(f"exists={status.exists} readable={status.readable} cookies={status.cookie_count}")
    print(f"offline_quality={status.offline_quality} has_li_at={status.has_li_at}")
    print(f"online_verified={status.online_verified} claims_authenticated={status.claims_authenticated}")
    if status.updated_at:
        print(f"updated_at={status.updated_at.isoformat()}")
    print(status.message)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    store = LinkedInSessionStore(settings.linkedin_storage_state_path)

    if args.command == "status":
        online_verified = False
        if getattr(args, "verify_online", False):
            if not getattr(args, "confirm_live_network", False):
                print(
                    "Refusing online verification without explicit consent. "
                    "Repeat with: status --verify-online --confirm-live-network",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            if not store.exists():
                print("Cannot verify online: session file missing.", file=sys.stderr)
                raise SystemExit(1)
            outcome = verify_online_feed_access(storage_state_path=store.path)
            online_verified = outcome == VerifyOutcome.LOGIN_SUCCESS
            print(f"online_probe_outcome={outcome.value}")
        status = store.status(online_verified=online_verified)
        _print_status(status, as_json=getattr(args, "json", False))
        code = 0
        if not status.readable and status.exists:
            code = 1
        elif online_verified and not status.claims_authenticated:
            code = 1
        raise SystemExit(code)

    if args.command == "logout":
        removed = store.delete()
        print("Session cleared." if removed else "No session file to remove.")
        raise SystemExit(0)

    if args.command == "prepare":
        store.ensure_parent()
        host_default = resolve_host_output_path(None)
        print("Manual LinkedIn authentication (safe path):")
        print("1. Confirm the new account works in the official LinkedIn mobile app (feed loads).")
        print("2. On your host (not Docker), install collector deps:")
        print("     pip install -r requirements-collector.txt")
        print("     playwright install chromium")
        print("3. Interactive desktop login (you complete any verification):")
        print("     python -m app.cli.linkedin_session login")
        print(f"   Validated session path: {host_default} (gitignored)")
        print("4. Optional offline check:")
        print("     python -m app.cli.linkedin_session status --json")
        print("5. Copy into Docker volume:")
        print("     python -m app.cli.linkedin_session install-docker")
        print("6. Optional one-shot online check inside configured environment:")
        print(
            "     python -m app.cli.linkedin_session status --verify-online --confirm-live-network"
        )
        print("7. Do NOT enable live collection until an operator authorizes activation.")
        raise SystemExit(0)

    if args.command == "login":
        out = resolve_host_output_path(args.output)
        outcome = run_interactive_login(out)
        if outcome != LoginOutcome.LOGIN_SUCCESS:
            raise SystemExit(1)
        print(f"Session saved (path only): {out}")
        print("Next: python -m app.cli.linkedin_session install-docker")
        raise SystemExit(0)

    if args.command == "install-docker":
        local = Path(args.from_path) if args.from_path else resolve_host_output_path(None)
        copy_storage_to_docker_volume(local, volume_name=args.volume)
        print(f"Session installed to Docker volume from: {local}")
        raise SystemExit(0)

    raise SystemExit(2)


if __name__ == "__main__":
    main()