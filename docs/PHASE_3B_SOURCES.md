# Phase 3B — Real job source feasibility

## Architecture (verified before 3B)

| Layer | Status |
|-------|--------|
| `JobSourceAdapter` + `AdapterFetchResult` | Contract stable; checkpoints, `has_more`, `metrics` (3B) |
| `JobNormalizer` → geography | `search_country_code` required; `country_code` from location only |
| `JobCollector` | Locks, retries, timeout, dry-run |
| LinkedIn | Playwright + HTML parsers; **proven offline fixtures only** |
| Celery | Fixture schedules only; `CELERY_ALLOW_LINKEDIN_TASKS=false` |
| REST API | Serves persisted jobs; new `source=greenhouse|lever|ashby` enum values |

### LinkedIn — offline vs unverified (no live access in 3B)

| Area | Offline-proven | Unverified live |
|------|----------------|-----------------|
| Search card CSS selectors | Fixture HTML | DOM drift, A/B layouts |
| Detail page parsing | Per-job fixtures | Lazy-loaded description |
| Pagination | Fixture pages | Infinite scroll / auth gates |
| Geography | Parser does not set job country from search market | Live location strings |
| Session | Storage-state file schema | Login, 2FA, challenges, bans |
| Compliance | N/A | LinkedIn User Agreement / automated access |

**Out of scope (not implemented):** CAPTCHA bypass, stealth, proxy rotation, account switching.

---

## Source comparison (public APIs)

### Greenhouse Job Board API

- **Endpoints:** `GET https://boards-api.greenhouse.io/v1/boards/{token}` and `.../jobs?content=true`
- **Auth:** None for public board tokens
- **Pagination:** Single list per board (client-side filter by keyword)
- **Fields:** `id`, `title`, `location.name`, `absolute_url`, `first_published`, `updated_at`, HTML `content`
- **Posted date:** use `first_published`; fallback `updated_at` only when missing
- **Source job ID:** stored as `{board_token}:{id}` to avoid cross-employer collisions
- **Rate limits:** Undocumented; use `PUBLIC_BOARD_MIN_INTERVAL_SECONDS`
- **Usage / redistribution:** Public board intended for job discovery; **aggregate republication may require employer/legal review** — not equivalent to unlimited commercial reuse
- **Integration:** **Implemented** — `GreenhouseJobSourceAdapter`

### Lever Postings API

- **Endpoint:** `GET https://api.lever.co/v0/postings/{site}?mode=json`
- **Auth:** None for public site slug
- **Pagination:** Offset/limit parameters on API (adapter uses full list + client filter)
- **Fields:** `id`, `text`, `categories.location`, `hostedUrl`, `descriptionPlain`, `createdAt`
- **Rate limits:** Undocumented; pace requests
- **Usage / redistribution:** Public postings for candidate use; verify Lever/customer terms before bulk redistribution
- **Integration:** **Implemented** — `LeverJobSourceAdapter` (offline fixtures + gated live)

### Ashby Public Job Posting API

- **Endpoint:** `GET https://api.ashbyhq.com/posting-api/job-board/{name}`
- **Auth:** None for public job board name
- **Fields:** `id`, `title`, `location`, `descriptionPlain`/`descriptionHtml`, `applyUrl`, `publishedAt`, `isListed`, `workplaceType`
- **Listing filter:** skip postings with `isListed: false`
- **Rate limits:** Undocumented
- **Usage / redistribution:** Public API for embedding job boards; confirm Ashby customer terms for third-party aggregation products
- **Integration:** **Implemented** — `AshbyJobSourceAdapter` (offline fixtures + gated live)

### LinkedIn (existing)

- Not a licensed public job API; browser scraping only; **remain disabled** for 3B.

---

## Operator workflow (no Beat, test DB)

```powershell
# Offline pipeline proof (no network)
docker compose exec api python -m app.cli.collect `
  --source greenhouse --board-site sample --country US --keyword engineer `
  --public-board-offline /app/tests/fixtures/public_boards/greenhouse/sample.json `
  --max-jobs 5 --mongo-db global_jobs_test

# Live public board (operator-approved ONLY)
# Set ALLOW_LIVE_PUBLIC_BOARD_COLLECTION=true in .env
docker compose exec api python -m app.cli.collect `
  --source greenhouse --board-site <public-board-token> --country US --keyword '*' `
  --confirm-live --max-jobs 5 --mongo-db global_jobs_test
```

Production `global_jobs` is blocked unless `ALLOW_COLLECTION_PRODUCTION_DB=true`.

---

## Quality metrics

Adapters populate `adapter_metrics` on each fetch (logged by `collect` CLI):

- `listings_seen`, `valid_listings`, `keyword_rejected`, `duplicate_skipped`
- `missing_description`, `missing_posted_at`
- `source`, board token/site id

Rejected normalization increments `CollectionStats.rejected_count` (invalid URL, missing `posted_at`, etc.).