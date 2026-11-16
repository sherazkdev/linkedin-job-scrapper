import re
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlparse

from pydantic import HttpUrl, ValidationError

from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.jobs.geography import normalize_search_country, resolve_geography
from app.modules.jobs.models.job import (
    EmploymentType,
    JobDataProvenance,
    JobDocument,
    JobSource,
    JobStatus,
    WorkplaceType,
)
from app.modules.jobs.posting_time import parse_posting_time


class JobNormalizationError(ValueError):
    pass


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


class JobNormalizer:
    """
    Baseline required fields: source_job_id, title, company, job_url, search_country_code.

    Optional / incomplete: posted_at, description body, resolved geography, employment metadata.
    Descriptions are never fabricated; empty description is stored when the source omits body text.
    """

    def __init__(self, source: JobSource) -> None:
        self._source = source

    def normalize(
        self,
        raw: RawJobRecord,
        *,
        observed_at: datetime | None = None,
        data_provenance: JobDataProvenance | None = None,
    ) -> JobDocument:
        if not raw.search_country_code:
            raise JobNormalizationError("search_country_code is required")
        try:
            search_country = normalize_search_country(raw.search_country_code)
        except ValueError as exc:
            raise JobNormalizationError(str(exc)) from exc

        url = self._validate_url(raw.job_url)
        now = observed_at or datetime.now(UTC)

        geo = resolve_geography(
            search_country_code=search_country,
            location_text=raw.location_text,
            city=raw.city,
            workplace_type=raw.workplace_type,
        )
        if raw.is_remote is not None:
            geo = replace(geo, is_remote=raw.is_remote, region=geo.region or raw.region)

        posted_at, source_label = parse_posting_time(
            iso_hint=raw.posting_time_iso_hint,
            relative_text=raw.posting_time_text or (None if raw.posted_at else None),
            reference=now,
        )
        if posted_at is None and raw.posted_at is not None:
            if raw.posted_at.tzinfo is None:
                raise JobNormalizationError("posted_at must be timezone-aware (UTC)")
            posted_at = raw.posted_at.astimezone(UTC)

        source_updated = raw.source_updated_at
        if source_updated is not None and source_updated.tzinfo is None:
            raise JobNormalizationError("source_updated_at must be timezone-aware (UTC)")
        if source_updated is not None:
            source_updated = source_updated.astimezone(UTC)

        employment = self._map_employment(raw.employment_type)
        workplace = self._map_workplace(raw.workplace_type)

        title = _collapse_ws(raw.title)
        company = _collapse_ws(raw.company)
        description = _collapse_ws(raw.description)
        if not title or not company:
            raise JobNormalizationError("title and company are required")

        source_job_id = raw.source_job_id.strip()
        if not source_job_id:
            raise JobNormalizationError("source_job_id is required")

        resolved_country = (
            raw.country_code.strip().upper() if raw.country_code else geo.country_code
        )
        if resolved_country is not None and (
            len(resolved_country) != 2 or not resolved_country.isalpha()
        ):
            raise JobNormalizationError("country_code must be ISO 3166-1 alpha-2 when provided")

        description_provided = raw.description_provided and bool(description)

        return JobDocument(
            source=self._source,
            source_job_id=source_job_id,
            title=title,
            company=company,
            search_country_code=search_country,
            country_code=resolved_country,
            location_text=geo.location_text,
            city=geo.city,
            region=geo.region or raw.region,
            is_remote=geo.is_remote,
            description=description,
            description_provided=description_provided,
            employment_type=employment,
            workplace_type=workplace,
            job_url=url,
            source_posting_label=source_label,
            source_updated_at=source_updated,
            posted_at=posted_at,
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.ACTIVE,
            data_provenance=data_provenance or JobDataProvenance.UNKNOWN,
        )

    @staticmethod
    def _validate_url(value: str) -> str:
        try:
            parsed = HttpUrl(value)
            url = str(parsed)
        except ValidationError as exc:
            raise JobNormalizationError("job_url is invalid") from exc
        scheme = urlparse(url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise JobNormalizationError("job_url must use http or https")
        return url

    @staticmethod
    def _map_employment(value: str | None) -> EmploymentType:
        if not value:
            return EmploymentType.OTHER
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return EmploymentType(key)
        except ValueError:
            return EmploymentType.OTHER

    @staticmethod
    def _map_workplace(value: str | None) -> WorkplaceType:
        if not value:
            return WorkplaceType.UNKNOWN
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return WorkplaceType(key)
        except ValueError:
            return WorkplaceType.UNKNOWN