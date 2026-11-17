from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="global-jobs", alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    mongo_uri: str = Field(alias="MONGO_URI")
    mongo_db_name: str = Field(default="global_jobs", alias="MONGO_DB_NAME")

    redis_url: str = Field(alias="REDIS_URL")

    allow_demo_seed: bool = Field(default=False, alias="ALLOW_DEMO_SEED")

    # Used by compose for Mongo init (not required in API process)
    mongo_root_user: str | None = Field(default=None, alias="MONGO_ROOT_USER")
    mongo_root_password: str | None = Field(default=None, alias="MONGO_ROOT_PASSWORD")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")

    jobs_default_page_size: int = 20
    jobs_max_page_size: int = 100
    jobs_max_page: int = Field(default=500, alias="JOBS_MAX_PAGE")
    api_cors_origins: str = Field(default="", alias="API_CORS_ORIGINS")
    mongo_server_selection_timeout_ms: int = Field(
        default=5000,
        alias="MONGO_SERVER_SELECTION_TIMEOUT_MS",
    )

    collection_lock_lease_seconds: int = Field(default=300, alias="COLLECTION_LOCK_LEASE_SECONDS")
    collection_adapter_timeout_seconds: int = Field(
        default=60,
        alias="COLLECTION_ADAPTER_TIMEOUT_SECONDS",
    )
    collection_max_retries: int = Field(default=2, alias="COLLECTION_MAX_RETRIES")
    allow_collection_production_db: bool = Field(
        default=False,
        alias="ALLOW_COLLECTION_PRODUCTION_DB",
    )

    allow_live_linkedin_collection: bool = Field(
        default=False,
        alias="ALLOW_LIVE_LINKEDIN_COLLECTION",
    )
    linkedin_storage_state_path: str = Field(
        default="/data/linkedin/storage_state.json",
        alias="LINKEDIN_STORAGE_STATE_PATH",
    )
    linkedin_browser_headless: bool = Field(default=True, alias="LINKEDIN_BROWSER_HEADLESS")
    linkedin_navigation_timeout_ms: int = Field(
        default=30_000,
        alias="LINKEDIN_NAVIGATION_TIMEOUT_MS",
    )
    linkedin_browser_launch_timeout_ms: int = Field(
        default=60_000,
        alias="LINKEDIN_BROWSER_LAUNCH_TIMEOUT_MS",
    )
    linkedin_selector_timeout_ms: int = Field(
        default=45_000,
        alias="LINKEDIN_SELECTOR_TIMEOUT_MS",
    )
    linkedin_page_operation_timeout_ms: int = Field(
        default=30_000,
        alias="LINKEDIN_PAGE_OPERATION_TIMEOUT_MS",
    )
    linkedin_browser_shutdown_grace_ms: int = Field(
        default=20_000,
        alias="LINKEDIN_BROWSER_SHUTDOWN_GRACE_MS",
    )
    linkedin_collection_adapter_timeout_seconds: int | None = Field(
        default=None,
        alias="LINKEDIN_COLLECTION_ADAPTER_TIMEOUT_SECONDS",
    )
    linkedin_offline_html_root: str | None = Field(
        default=None,
        alias="LINKEDIN_OFFLINE_HTML_ROOT",
    )
    linkedin_max_live_jobs_per_run: int = Field(
        default=5,
        alias="LINKEDIN_MAX_LIVE_JOBS_PER_RUN",
    )
    linkedin_filter_past_24_hours: bool = Field(
        default=True,
        alias="LINKEDIN_FILTER_PAST_24_HOURS",
    )
    linkedin_max_search_pages_per_run: int = Field(
        default=5,
        alias="LINKEDIN_MAX_SEARCH_PAGES_PER_RUN",
    )
    linkedin_max_detail_opens_per_run: int = Field(
        default=40,
        alias="LINKEDIN_MAX_DETAIL_OPENS_PER_RUN",
    )

    allow_live_public_board_collection: bool = Field(
        default=False,
        alias="ALLOW_LIVE_PUBLIC_BOARD_COLLECTION",
    )
    public_board_http_timeout_seconds: int = Field(
        default=30,
        alias="PUBLIC_BOARD_HTTP_TIMEOUT_SECONDS",
    )
    public_board_min_interval_seconds: float = Field(
        default=1.0,
        alias="PUBLIC_BOARD_MIN_INTERVAL_SECONDS",
    )
    public_board_max_jobs_per_run: int = Field(
        default=5,
        alias="PUBLIC_BOARD_MAX_JOBS_PER_RUN",
    )
    public_board_offline_fixture_root: str | None = Field(
        default=None,
        alias="PUBLIC_BOARD_OFFLINE_FIXTURE_ROOT",
    )

    allow_live_market_search_collection: bool = Field(
        default=False,
        alias="ALLOW_LIVE_MARKET_SEARCH_COLLECTION",
    )
    adzuna_app_id: str | None = Field(default=None, alias="ADZUNA_APP_ID")
    adzuna_app_key: str | None = Field(default=None, alias="ADZUNA_APP_KEY")
    market_search_http_timeout_seconds: int = Field(
        default=30,
        alias="MARKET_SEARCH_HTTP_TIMEOUT_SECONDS",
    )
    market_search_min_interval_seconds: float = Field(
        default=1.0,
        alias="MARKET_SEARCH_MIN_INTERVAL_SECONDS",
    )
    market_search_max_jobs_per_run: int = Field(
        default=5,
        alias="MARKET_SEARCH_MAX_JOBS_PER_RUN",
    )
    adzuna_max_pages_per_run: int = Field(default=2, alias="ADZUNA_MAX_PAGES_PER_RUN")
    adzuna_results_per_page: int = Field(default=20, alias="ADZUNA_RESULTS_PER_PAGE")
    market_search_offline_fixture_root: str | None = Field(
        default=None,
        alias="MARKET_SEARCH_OFFLINE_FIXTURE_ROOT",
    )

    # Celery / scheduler (Phase 2C — fixture-only by default)
    celery_broker_url: str | None = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")
    celery_task_default_queue: str = Field(default="collection", alias="CELERY_TASK_DEFAULT_QUEUE")
    celery_worker_concurrency: int = Field(default=2, alias="CELERY_WORKER_CONCURRENCY")
    celery_beat_dispatch_interval_seconds: int = Field(
        default=120,
        alias="CELERY_BEAT_DISPATCH_INTERVAL_SECONDS",
    )
    celery_target_cooldown_seconds: int = Field(
        default=3600,
        alias="CELERY_TARGET_COOLDOWN_SECONDS",
    )
    celery_collection_max_jobs_default: int = Field(
        default=10,
        alias="CELERY_COLLECTION_MAX_JOBS_DEFAULT",
    )
    celery_allow_linkedin_tasks: bool = Field(default=False, alias="CELERY_ALLOW_LINKEDIN_TASKS")
    celery_worker_mongo_db_name: str = Field(
        default="global_jobs_test",
        alias="CELERY_WORKER_MONGO_DB_NAME",
    )
    celery_task_time_limit: int = Field(default=600, alias="CELERY_TASK_TIME_LIMIT")
    celery_task_soft_time_limit: int = Field(default=540, alias="CELERY_TASK_SOFT_TIME_LIMIT")
    celery_task_max_retries: int = Field(default=3, alias="CELERY_TASK_MAX_RETRIES")
    celery_lock_lease_seconds: int = Field(default=300, alias="CELERY_LOCK_LEASE_SECONDS")
    celery_dispatch_max_per_tick: int = Field(
        default=1,
        ge=1,
        le=50,
        alias="CELERY_DISPATCH_MAX_PER_TICK",
    )
    celery_linkedin_access_pause_seconds: int = Field(
        default=86400,
        alias="CELERY_LINKEDIN_ACCESS_PAUSE_SECONDS",
    )
    allow_collection_target_index_migration: bool = Field(
        default=False,
        alias="ALLOW_COLLECTION_TARGET_INDEX_MIGRATION",
    )
    celery_dispatch_source_allowlist: str | None = Field(
        default=None,
        alias="CELERY_DISPATCH_SOURCE_ALLOWLIST",
    )
    celery_dispatch_fair_country_coverage: bool = Field(
        default=True,
        alias="CELERY_DISPATCH_FAIR_COUNTRY_COVERAGE",
    )
    linkedin_max_live_runs_per_24h: int = Field(
        default=30,
        ge=0,
        le=500,
        alias="LINKEDIN_MAX_LIVE_RUNS_PER_24H",
        description="Hard cap on live LinkedIn collection runs started in any rolling 24h window.",
    )
    pilot_mongo_db_name: str = Field(
        default="global_jobs_pilot",
        alias="PILOT_MONGO_DB_NAME",
    )
    allow_pilot_to_production_promotion: bool = Field(
        default=False,
        alias="ALLOW_PILOT_TO_PRODUCTION_PROMOTION",
    )
    promotion_target_mongo_db_name: str = Field(
        default="global_jobs",
        alias="PROMOTION_TARGET_MONGO_DB_NAME",
    )

    internal_ops_token: str | None = Field(default=None, alias="INTERNAL_OPS_TOKEN")
    job_stale_after_days: int = Field(
        default=0,
        alias="JOB_STALE_AFTER_DAYS",
        description="0 disables automatic stale listing; operator CLI only",
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
