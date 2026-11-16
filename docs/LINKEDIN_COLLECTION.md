# LinkedIn-only collection (primary business path)

## Scope

- **Source:** LinkedIn public/authenticated job search only (no Adzuna/Jooble/Careerjet).
- **Targets:** `config/global_jobs_40_countries_50_keywords_manifest.json` (40×50 = 2,000 pairs).
- **Recency:** Past 24 hours (`f_TPR=r86400` on search URL when `LINKEDIN_FILTER_PAST_24_HOURS=true`, default).
- **Scheduling:** CLI or optional Celery when explicitly enabled — **never** all 2,000 targets at once.

## Geography

- `search_country_code` = manifest ISO market (e.g. `PK`).
- `country_code` = resolved from `location_text` via normalizer (nullable if unknown).
- Search `location` query uses manifest country **name** (e.g. Pakistan).

## Offline verification (default)

```powershell
docker compose exec api python -m app.cli.collect --source linkedin --country PK `
  --keyword "Software Engineer" --max-jobs 5 --dry-run `
  --linkedin-offline-html /app/app/modules/collection/linkedin/fixtures `
  --mongo-db global_jobs_test
```

## Checkpoint / resume

Progress is stored in MongoDB `collection_checkpoints` (replaces legacy `scraper_progress.txt`).

```powershell
docker compose exec api python -m app.cli.linkedin_progress --mongo-db global_jobs_test
```

## Session setup (host workstation)

`prepare` prints instructions only. To open a **headed** browser:

```powershell
.\.venv\Scripts\python -m app.cli.linkedin_session login
.\.venv\Scripts\python -m app.cli.linkedin_session install-docker
docker compose --profile collector run --rm collector python -m app.cli.linkedin_session status
```

Session file: `data/linkedin/storage_state.json` (gitignored).

## Collector image vs workspace code

The collector image bakes a copy of `app/` at build time. If `collect --help` lacks `--confirm-live` / `--location`, or imports like `search_page_diagnostics` fail, rebuild or **bind-mount** current code:

```powershell
docker compose --profile collector build collector
# or on every run until rebuild succeeds:
$mount = "-v ${PWD}/app:/app/app:ro"
```

## Operator-approved live test (5 jobs, PK) — **not run automatically**

Prerequisites:

1. Valid LinkedIn session in `global_jobs_linkedin_auth` (see above).
2. `ALLOW_LIVE_LINKEDIN_COLLECTION=true`
3. `--confirm-live` on collect command.
4. Database: `global_jobs_test` only.
5. Current parser in container (rebuild or `-v .../app:/app/app:ro`).

Diagnostics (operator-approved live HTTP only):

```powershell
docker compose --profile collector run --rm -v "${PWD}/app:/app/app:ro" `
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true `
  collector python -m app.cli.linkedin_debug_search
```

Inspect `diagnostics=` (`job_view_links`, `genuine_empty`) and `cards_parsed` before collect.

```powershell
docker compose --profile collector run --rm `
  -v "${PWD}/app:/app/app:ro" `
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true `
  -e COLLECTION_ADAPTER_TIMEOUT_SECONDS=600 `
  collector python -m app.cli.collect --source linkedin --country PK `
  --location "Islamabad, Pakistan" `
  --keyword "Software Engineer" --max-jobs 5 --confirm-live `
  --mongo-db global_jobs_test
```

## API verification (test DB)

```powershell
# Point a test API container at global_jobs_test, then:
curl.exe "http://127.0.0.1:18085/api/v1/jobs?source=linkedin&search_country_code=PK&sort=posted_at_desc"
```

## Blockers (report, do not bypass)

- Auth wall / login required
- Verification challenge
- Session expired
- Rate limiting
- DOM structure changes

No CAPTCHA bypass, account rotation, or stealth automation.