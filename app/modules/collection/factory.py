from pathlib import Path
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.modules.collection.adapters.fixture import FixtureJobSourceAdapter
from app.modules.collection.repositories.checkpoint_repository import CheckpointRepository
from app.modules.collection.repositories.run_repository import RunRepository
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.collection.services.collector import JobCollector
from app.modules.collection.services.error_handler import CollectionErrorHandler
from app.modules.collection.services.normalizer import JobNormalizer
from app.modules.collection.services.persistence import JobPersistenceService
from app.modules.collection.services.run_service import CollectionRunService
from app.modules.jobs.models.job import JobSource
from app.modules.jobs.repositories.job_repository import JobRepository

PUBLIC_BOARD_SOURCES = frozenset({JobSource.GREENHOUSE, JobSource.LEVER, JobSource.ASHBY})
MARKET_SEARCH_SOURCES = frozenset({JobSource.ADZUNA})


def _linkedin_live_adapter_timeout_seconds(settings: Settings) -> int:
    nav_s = settings.linkedin_navigation_timeout_ms / 1000
    sel_s = settings.linkedin_selector_timeout_ms / 1000
    op_s = settings.linkedin_page_operation_timeout_ms / 1000
    search_budget = nav_s + sel_s + (op_s * 2) + 15
    detail_budget = nav_s + op_s + 5
    job_cap = max(1, settings.linkedin_max_live_jobs_per_run)
    estimated = int(search_budget + (detail_budget * job_cap) + 30)
    return max(settings.collection_adapter_timeout_seconds, estimated)


def _offline_board_fixture(
    settings: Settings,
    source: JobSource,
    board_token: str,
    explicit: Path | None,
) -> Path | None:
    if explicit is not None:
        return explicit
    if settings.public_board_offline_fixture_root:
        candidate = (
            Path(settings.public_board_offline_fixture_root)
            / source.value
            / f"{board_token.lower()}.json"
        )
        if candidate.exists():
            return candidate
    return None


def resolve_adapter(
    source: JobSource,
    settings: Settings,
    *,
    linkedin_offline_html_root: Path | None = None,
    board_token: str | None = None,
    public_board_offline_fixture: Path | None = None,
    market_search_offline_fixture: Path | None = None,
):
    if source == JobSource.FIXTURE:
        return FixtureJobSourceAdapter()
    if source == JobSource.LINKEDIN:
        from app.modules.collection.linkedin.adapter import LinkedInJobSourceAdapter

        offline_root = linkedin_offline_html_root
        if offline_root is None and settings.linkedin_offline_html_root:
            offline_root = Path(settings.linkedin_offline_html_root)
        browser = None
        if settings.allow_live_linkedin_collection:
            from app.modules.collection.browser.manager import BrowserManager

            browser = BrowserManager(
                headless=settings.linkedin_browser_headless,
                launch_timeout_ms=settings.linkedin_browser_launch_timeout_ms,
                navigation_timeout_ms=settings.linkedin_navigation_timeout_ms,
                storage_state_path=settings.linkedin_storage_state_path,
                shutdown_grace_ms=settings.linkedin_browser_shutdown_grace_ms,
            )
        return LinkedInJobSourceAdapter(
            settings=settings,
            browser=browser,
            offline_html_root=offline_root,
            live_enabled=settings.allow_live_linkedin_collection,
            filter_past_24_hours=settings.linkedin_filter_past_24_hours,
        )
    if source in PUBLIC_BOARD_SOURCES:
        if not board_token:
            raise ValueError(f"board_token is required for source {source.value}")
        live_enabled = settings.allow_live_public_board_collection
        offline = _offline_board_fixture(
            settings, source, board_token, public_board_offline_fixture
        )
        if source == JobSource.GREENHOUSE:
            from app.modules.collection.adapters.greenhouse import GreenhouseJobSourceAdapter

            return GreenhouseJobSourceAdapter(
                settings=settings,
                board_token=board_token,
                offline_fixture=offline,
                live_enabled=live_enabled,
            )
        if source == JobSource.LEVER:
            from app.modules.collection.adapters.lever import LeverJobSourceAdapter

            return LeverJobSourceAdapter(
                settings=settings,
                board_token=board_token,
                offline_fixture=offline,
                live_enabled=live_enabled,
            )
        from app.modules.collection.adapters.ashby import AshbyJobSourceAdapter

        return AshbyJobSourceAdapter(
            settings=settings,
            board_token=board_token,
            offline_fixture=offline,
            live_enabled=live_enabled,
        )
    if source == JobSource.ADZUNA:
        from app.modules.collection.adapters.adzuna import AdzunaJobSourceAdapter

        return AdzunaJobSourceAdapter(
            settings=settings,
            offline_fixture=market_search_offline_fixture,
            live_enabled=settings.allow_live_market_search_collection,
        )
    raise ValueError(f"Unsupported collection source: {source.value}")


def build_collector(
    database: AsyncDatabase[Any],
    settings: Settings,
    source: JobSource,
    *,
    linkedin_offline_html_root: Path | None = None,
    board_token: str | None = None,
    public_board_offline_fixture: Path | None = None,
    market_search_offline_fixture: Path | None = None,
    target_cooldown_seconds: int = 0,
    linkedin_access_pause_seconds: int = 86400,
) -> JobCollector:
    adapter = resolve_adapter(
        source,
        settings,
        linkedin_offline_html_root=linkedin_offline_html_root,
        board_token=board_token,
        public_board_offline_fixture=public_board_offline_fixture,
        market_search_offline_fixture=market_search_offline_fixture,
    )
    adapter_timeout_seconds = settings.collection_adapter_timeout_seconds
    if source == JobSource.LINKEDIN and settings.allow_live_linkedin_collection:
        if settings.linkedin_collection_adapter_timeout_seconds is not None:
            adapter_timeout_seconds = settings.linkedin_collection_adapter_timeout_seconds
        else:
            adapter_timeout_seconds = _linkedin_live_adapter_timeout_seconds(settings)

    return JobCollector(
        adapter=adapter,
        normalizer=JobNormalizer(source),
        persistence=JobPersistenceService(JobRepository(database)),
        run_service=CollectionRunService(RunRepository(database)),
        checkpoint_repository=CheckpointRepository(database),
        target_repository=TargetRepository(database),
        error_handler=CollectionErrorHandler(),
        lock_lease_seconds=settings.collection_lock_lease_seconds,
        adapter_timeout_seconds=adapter_timeout_seconds,
        max_adapter_retries=settings.collection_max_retries,
        target_success_cooldown_seconds=target_cooldown_seconds,
        linkedin_access_pause_seconds=linkedin_access_pause_seconds,
    )