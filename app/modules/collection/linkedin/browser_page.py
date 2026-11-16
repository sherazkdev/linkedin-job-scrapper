"""Bounded Playwright page lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

DEFAULT_PAGE_CLOSE_GRACE_MS = 10_000


async def close_page_bounded(
    page: Page,
    *,
    grace_ms: int = DEFAULT_PAGE_CLOSE_GRACE_MS,
) -> None:
    try:
        await asyncio.wait_for(page.close(), timeout=grace_ms / 1000)
    except TimeoutError:
        logger.warning("page.close exceeded grace_ms=%s", grace_ms)
    except Exception as exc:
        logger.warning("page.close failed error=%s", exc.__class__.__name__)