"""Host-side interactive LinkedIn login (headed Chromium). Not for use inside Docker."""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HOST_STORAGE = Path("data/linkedin/storage_state.json")
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"


def running_in_container() -> bool:
    return Path("/.dockerenv").is_file()


def resolve_host_output_path(override: str | None) -> Path:
    if override:
        return Path(override)
    return DEFAULT_HOST_STORAGE.resolve()


def run_interactive_login(
    output_path: Path,
    *,
    start_url: str = LINKEDIN_LOGIN_URL,
) -> None:
    """Open a visible browser; operator completes login manually; save storage state."""
    if running_in_container():
        raise SystemExit(
            "Interactive login must run on your host workstation, not inside the collector "
            "container. Use: python -m app.cli.linkedin_session login"
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. On the host: pip install -r requirements-collector.txt "
            "&& playwright install chromium"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Opening Chromium (headed). Complete LinkedIn sign-in in the browser window.")
    print("A Chromium window will open. Sign in to LinkedIn (including any verification).")
    print("When you see your feed or home page, return here and press Enter to save the session.")
    print("(Secrets are not printed.)")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(start_url, wait_until="domcontentloaded")
        try:
            input("Press Enter after you have finished signing in... ")
        except EOFError:
            print("Non-interactive terminal; waiting up to 15 minutes for login...", file=sys.stderr)
            page.wait_for_url("**/feed/**", timeout=900_000)
        context.storage_state(path=str(output_path))
        browser.close()

    logger.info("Session saved to %s", output_path)