"""Host-side interactive LinkedIn login (headed Chromium). Not for use inside Docker."""

import logging
import sys
import tempfile
from pathlib import Path

from app.modules.collection.linkedin.session_validation import (
    LoginOutcome,
    atomic_save_storage_state,
    classify_live_page,
    inspect_offline_storage_state,
)

__all__ = ["LoginOutcome", "DEFAULT_HOST_STORAGE", "resolve_host_output_path", "run_interactive_login"]

logger = logging.getLogger(__name__)

DEFAULT_HOST_STORAGE = Path("data/linkedin/storage_state.json")
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
FEED_PROBE_URL = "https://www.linkedin.com/feed/"


def running_in_container() -> bool:
    return Path("/.dockerenv").is_file()


def resolve_host_output_path(override: str | None) -> Path:
    if override:
        return Path(override)
    return DEFAULT_HOST_STORAGE.resolve()


def validate_browser_session(page) -> LoginOutcome:
    """Evaluate current browser page — does not navigate or submit credentials."""
    try:
        url = page.url or ""
        html = page.content()
    except Exception:
        return LoginOutcome.NETWORK_ERROR
    return classify_live_page(url=url, html=html)


def run_interactive_login(
    output_path: Path,
    *,
    start_url: str = LINKEDIN_LOGIN_URL,
) -> LoginOutcome:
    """Open a visible browser; operator completes login manually; save only if validated."""
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
    print("A Chromium window will open. Sign in to LinkedIn (complete any verification yourself).")
    print("When your feed or home page loads, return here and press Enter.")
    print("The session will NOT be saved if login is incomplete or verification is pending.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=120_000)
        except Exception as exc:
            browser.close()
            logger.error("Navigation failed: %s", exc.__class__.__name__)
            return LoginOutcome.NETWORK_ERROR
        try:
            input("Press Enter after you have finished signing in... ")
        except EOFError:
            print("Non-interactive terminal; waiting up to 15 minutes for feed URL...", file=sys.stderr)
            try:
                page.wait_for_url("**/feed/**", timeout=900_000)
            except Exception:
                browser.close()
                return LoginOutcome.LOGIN_INCOMPLETE

        outcome = validate_browser_session(page)
        if outcome != LoginOutcome.LOGIN_SUCCESS:
            try:
                page.goto(FEED_PROBE_URL, wait_until="domcontentloaded", timeout=60_000)
                outcome = validate_browser_session(page)
            except Exception:
                pass

        if outcome != LoginOutcome.LOGIN_SUCCESS:
            print(
                f"Login NOT saved: outcome={outcome.value}. "
                "Complete authentication in the browser and try again."
            )
            browser.close()
            return outcome

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".json",
            dir=str(output_path.parent),
        ) as tmp:
            tmp_path = Path(tmp.name)
        context.storage_state(path=str(tmp_path))
        browser.close()

        offline = inspect_offline_storage_state(tmp_path)
        if offline.quality.value in {"empty", "corrupt", "unlikely_authenticated"}:
            tmp_path.unlink(missing_ok=True)
            print(f"Login NOT saved: offline quality={offline.quality.value}")
            return LoginOutcome.LOGIN_INCOMPLETE

        try:
            atomic_save_storage_state(
                source_path=tmp_path,
                destination=output_path,
                backup=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    logger.info("Validated session saved to %s", output_path)
    print(f"Saved validated session: outcome={LoginOutcome.LOGIN_SUCCESS.value}")
    return LoginOutcome.LOGIN_SUCCESS