"""
Run a single collection target.

Usage:
  python -m app.cli.collect --source fixture --country DE --keyword "backend engineer"
  python -m app.cli.collect --source greenhouse --board-site sample \\
      --country US --keyword engineer \\
      --public-board-offline PATH/TO/greenhouse/sample.json
"""

import argparse
import asyncio
import logging
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.collection.factory import (
    MARKET_SEARCH_SOURCES,
    PUBLIC_BOARD_SOURCES,
    build_collector,
)
from app.modules.collection.http.errors import PublicBoardCollectionError
from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource
from app.modules.jobs.provenance import resolve_collection_provenance

logger = logging.getLogger(__name__)

SOURCE_MAP = {
    "fixture": JobSource.FIXTURE,
    "demo": JobSource.DEMO,
    "linkedin": JobSource.LINKEDIN,
    "greenhouse": JobSource.GREENHOUSE,
    "lever": JobSource.LEVER,
    "ashby": JobSource.ASHBY,
    "adzuna": JobSource.ADZUNA,
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single job collection target")
    parser.add_argument("--source", required=True, choices=sorted(SOURCE_MAP.keys()))
    parser.add_argument("--country", required=True, help="ISO 3166-1 alpha-2 search market code")
    parser.add_argument(
        "--keyword",
        required=True,
        help="Title filter (use * to accept all titles)",
    )
    parser.add_argument("--max-jobs", type=int, default=10, dest="max_jobs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate pipeline without Mongo writes",
    )
    parser.add_argument(
        "--mongo-db",
        dest="mongo_db",
        default=None,
        help="Override Mongo database name",
    )
    parser.add_argument(
        "--run-owner",
        default="cli",
        help="Lock owner id for concurrent safeguards",
    )
    parser.add_argument(
        "--board-site",
        dest="board_site",
        default=None,
        help="Public board token/site slug (Greenhouse/Lever/Ashby)",
    )
    parser.add_argument(
        "--public-board-offline",
        dest="public_board_offline",
        default=None,
        help="Offline JSON fixture for public board adapter (no network)",
    )
    parser.add_argument(
        "--linkedin-offline-html",
        dest="linkedin_offline_html",
        default=None,
        help="Replay LinkedIn HTML fixtures (offline; no network)",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        dest="confirm_live",
        help="Explicit operator acknowledgment for live network collection",
    )
    parser.add_argument(
        "--location",
        default=None,
        help="LinkedIn search location override (e.g. 'Islamabad, Pakistan')",
    )
    parser.add_argument(
        "--market-search-offline",
        dest="market_search_offline",
        default=None,
        help="Offline JSON fixture for market-search adapter (Adzuna)",
    )
    return parser.parse_args(argv)


def _validate_database_access(settings: Settings, db_name: str) -> None:
    if db_name == settings.mongo_db_name and not settings.allow_collection_production_db:
        raise SystemExit(
            "Refusing to write collection results to production database "
            f"'{db_name}'. Use --mongo-db global_jobs_test or set "
            "ALLOW_COLLECTION_PRODUCTION_DB=true."
        )


def _require_board_site(source: JobSource, board_site: str | None) -> str:
    if source not in PUBLIC_BOARD_SOURCES:
        return ""
    if not board_site or not board_site.strip():
        raise SystemExit(f"--board-site is required for source {source.value}")
    return board_site.strip()


async def run_collect(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    source = SOURCE_MAP[args.source]
    board_site = _require_board_site(source, args.board_site)

    linkedin_offline: Path | None = None
    if args.linkedin_offline_html:
        linkedin_offline = Path(args.linkedin_offline_html)
    elif settings.linkedin_offline_html_root:
        linkedin_offline = Path(settings.linkedin_offline_html_root)

    public_offline: Path | None = (
        Path(args.public_board_offline) if args.public_board_offline else None
    )
    market_offline: Path | None = (
        Path(args.market_search_offline) if args.market_search_offline else None
    )

    if source == JobSource.LINKEDIN:
        if settings.allow_live_linkedin_collection:
            if linkedin_offline is not None:
                logger.warning("Live flag set but offline HTML provided; using fixture replay only")
            else:
                if not args.confirm_live:
                    raise SystemExit(
                        "Live LinkedIn collection requires --confirm-live on the command line "
                        "in addition to ALLOW_LIVE_LINKEDIN_COLLECTION=true."
                    )
                logger.warning(
                    "Live LinkedIn mode acknowledged by operator; max jobs capped to %s",
                    settings.linkedin_max_live_jobs_per_run,
                )
                args.max_jobs = min(args.max_jobs, settings.linkedin_max_live_jobs_per_run)
        elif linkedin_offline is None:
            raise SystemExit(
                "LinkedIn collection requires offline HTML fixtures "
                "(--linkedin-offline-html) unless ALLOW_LIVE_LINKEDIN_COLLECTION=true."
            )

    if source in PUBLIC_BOARD_SOURCES:
        offline_ok = public_offline is not None or (
            settings.public_board_offline_fixture_root is not None
            and (
                Path(settings.public_board_offline_fixture_root)
                / source.value
                / f"{board_site.lower()}.json"
            ).exists()
        )
        if settings.allow_live_public_board_collection:
            if not args.confirm_live and not offline_ok:
                raise SystemExit(
                    "Live public board collection requires --confirm-live unless "
                    "a public board offline fixture is provided."
                )
            logger.warning(
                "Live public board fetch acknowledged; max jobs capped to %s",
                settings.public_board_max_jobs_per_run,
            )
            args.max_jobs = min(args.max_jobs, settings.public_board_max_jobs_per_run)
        elif not offline_ok:
            raise SystemExit(
                "Public board collection requires an offline fixture "
                "(--public-board-offline) unless ALLOW_LIVE_PUBLIC_BOARD_COLLECTION=true."
            )

    if source in MARKET_SEARCH_SOURCES:
        offline_ok = market_offline is not None or (
            settings.market_search_offline_fixture_root is not None
            and (
                Path(settings.market_search_offline_fixture_root)
                / "adzuna"
                / f"{args.country.lower()}_page1.json"
            ).exists()
        )
        if settings.allow_live_market_search_collection:
            if not args.confirm_live and not offline_ok:
                raise SystemExit(
                    "Live market-search collection requires --confirm-live unless "
                    "an offline fixture is provided (--market-search-offline)."
                )
            logger.warning(
                "Live market-search acknowledged; max jobs capped to %s",
                settings.market_search_max_jobs_per_run,
            )
            args.max_jobs = min(args.max_jobs, settings.market_search_max_jobs_per_run)
        elif not offline_ok:
            raise SystemExit(
                "Market-search collection requires an offline fixture "
                "(--market-search-offline) unless ALLOW_LIVE_MARKET_SEARCH_COLLECTION=true."
            )

    write_sources = {
        JobSource.FIXTURE,
        JobSource.LINKEDIN,
        *PUBLIC_BOARD_SOURCES,
        *MARKET_SEARCH_SOURCES,
    }
    db_name = args.mongo_db or settings.mongo_db_name
    if (
        source in write_sources
        and not args.dry_run
        and db_name == settings.mongo_db_name
        and not settings.allow_collection_production_db
    ):
        db_name = f"{settings.mongo_db_name}_test"
        logger.warning("Collection redirected to isolated database '%s'", db_name)
    if not args.dry_run:
        _validate_database_access(settings, db_name)

    max_jobs = max(1, min(args.max_jobs, 500))

    async with open_database(db_name) as database:
        target_repo = TargetRepository(database)
        if source == JobSource.FIXTURE:
            await target_repo.ensure_defaults()
        if source in {JobSource.LINKEDIN, *PUBLIC_BOARD_SOURCES, *MARKET_SEARCH_SOURCES}:
            await target_repo.upsert_target(
                source=source,
                country_code=args.country,
                keyword=args.keyword,
            )
        used_offline_fixture = source == JobSource.FIXTURE
        live_network_used = False
        if source == JobSource.LINKEDIN:
            used_offline_fixture = linkedin_offline is not None
            live_network_used = (
                settings.allow_live_linkedin_collection
                and args.confirm_live
                and linkedin_offline is None
            )
        elif source in PUBLIC_BOARD_SOURCES:
            offline_ok = public_offline is not None or (
                settings.public_board_offline_fixture_root is not None
                and board_site
                and (
                    Path(settings.public_board_offline_fixture_root)
                    / source.value
                    / f"{board_site.lower()}.json"
                ).exists()
            )
            used_offline_fixture = offline_ok
            live_network_used = (
                settings.allow_live_public_board_collection
                and args.confirm_live
                and not offline_ok
            )
        elif source in MARKET_SEARCH_SOURCES:
            offline_ok = market_offline is not None
            used_offline_fixture = offline_ok
            live_network_used = (
                settings.allow_live_market_search_collection
                and args.confirm_live
                and not offline_ok
            )
        data_provenance = resolve_collection_provenance(
            source,
            used_offline_fixture=used_offline_fixture,
            live_network_used=live_network_used,
        )

        if (
            market_offline is None
            and settings.market_search_offline_fixture_root
            and source in MARKET_SEARCH_SOURCES
        ):
            auto = (
                Path(settings.market_search_offline_fixture_root)
                / "adzuna"
                / f"{args.country.lower()}_page1.json"
            )
            if auto.exists():
                market_offline = auto

        collector = build_collector(
            database,
            settings,
            source,
            linkedin_offline_html_root=linkedin_offline,
            board_token=board_site or None,
            public_board_offline_fixture=public_offline,
            market_search_offline_fixture=market_offline,
        )
        try:
            summary = await collector.collect(
                source=source,
                country_code=args.country,
                keyword=args.keyword,
                max_jobs=max_jobs,
                dry_run=args.dry_run,
                run_owner=args.run_owner,
                data_provenance=data_provenance,
                search_location=args.location,
            )
        finally:
            await collector.shutdown()

    logger.info(
        "Collection finished run_id=%s dry_run=%s stats=%s adapter_metrics=%s",
        summary.get("run_id"),
        summary.get("dry_run"),
        summary.get("stats"),
        summary.get("adapter_metrics"),
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run_collect()))
    except KeyboardInterrupt:
        logger.info("Collection interrupted")
        raise SystemExit(130) from None
    except LinkedInCollectionError as exc:
        logger.error("LinkedIn collection blocked state=%s", exc.state.value)
        raise SystemExit(3) from exc
    except PublicBoardCollectionError as exc:
        logger.error("Public board collection blocked state=%s", exc.state.value)
        raise SystemExit(4) from exc
    except Exception:
        logger.exception("Collection failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()