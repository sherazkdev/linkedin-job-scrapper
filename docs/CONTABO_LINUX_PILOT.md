# Contabo Linux VPS — isolated LinkedIn pilot (operator runbook)

Do **not** run this on Windows/WSL for live LinkedIn. Use a **native Linux** Docker host.

## Prerequisites (before SSH changes)

| Item | Requirement |
|------|-------------|
| SSH | Operator SSH key to Contabo; **no credentials in git** |
| Isolation | Separate Compose project name, e.g. `linkedin-pilot` — do not attach to existing prod `global_jobs` volumes |
| RAM | **≥ 4 GB** free for host; worker `mem_limit: 2g` (see overlay) |
| Disk | **≥ 20 GB** free; monitor for Chromium crash dumps under `/var/lib/docker` |
| Docker | Engine 24+ and Compose v2 |
| Session | Copy **only** `storage_state.json` into a **new** volume (never commit); verify cookie count without printing values |
| Mongo | **Separate** DB name e.g. `global_jobs_pilot` on a **new** volume OR dedicated Mongo container in pilot project |
| Redis | Pilot-project Redis only (no shared prod broker) |
| Beat | **Must stay off** for single-shot pilot |
| Env | `CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin`, `CELERY_DISPATCH_MAX_PER_TICK=1`, live flags **only** on worker for the one run |

## Diagnosis: manual CLI vs Celery (same codebase)

| Dimension | Manual `collector` CLI | Celery `worker-linkedin` |
|-----------|------------------------|----------------------------|
| Image | `Dockerfile.collector` | Same image |
| Browser | `BrowserManager` → Playwright Chromium bundled in image | Same |
| Async entry | `asyncio.run(collect)` | `asyncio.run(_collect_async)` in solo worker |
| Pool | N/A (one-shot container) | **`--pool=solo`** (required) |
| Extra steps | Direct `collector.collect` | Target lock + `collection_runs` + same `collect` |
| Session path | `/data/linkedin/storage_state.json` volume | Same volume mount |
| Timeouts (fixed) | Docs: `COLLECTION_ADAPTER_TIMEOUT_SECONDS=600` | Compose now sets **600** + LinkedIn ms vars |
| `page_unresponsive` | Fails when selector waits **45s** then `document.readyState` probe fails | Same code path (`search_page_capture.py`) |
| WSL Windows | Chromium crash dumps on C: (observed **~9 GB**/run) | **Do not use for live** |

### `--no-sandbox` / `--disable-dev-shm-usage`

Required for Chromium inside Docker as non-root. **Security:** reduces browser sandbox isolation; acceptable **only** inside dedicated collector/worker containers on an isolated VPS network — not on shared multi-tenant hosts without network isolation.

## VPS preflight commands (read-only)

Run on Contabo **before** pilot deploy:

```bash
uname -a && free -h && df -h && swapon --show
docker version && docker compose version
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Confirm **no** port clash with existing Nginx/API (8085/443). Use pilot-only ports or internal bridge only.

## One-shot live pilot (after explicit approval)

1. `docker compose -f compose.yaml -f compose.contabo-pilot.yaml -p linkedin-pilot --profile celery-linkedin up -d worker-linkedin` with `ALLOW_LIVE_*` **false** in file.
2. Sync session to pilot volume (scp/rsync `storage_state.json` into volume mount path).
3. Enable **one** target in pilot Mongo (`enabled=true`, `max_jobs_per_run=1`, location + keyword).
4. Start **temporary** live worker override container (same as local `run -d -e ALLOW_LIVE_LINKEDIN_COLLECTION=true …`) — **not** Beat.
5. `python -m app.cli.celery_ops dispatch-once` once.
6. Record: Celery task id, `collection_runs`, duration, `docker stats` peak RSS, worker logs (`Chromium launched`, `search_nav`, errors).
7. **Disable target** and set live env **false**; stop pilot worker regardless of outcome.
8. Query pilot API / Mongo — **never** prod `global_jobs`.

## Success criteria for enabling Beat / wider scheduling

- One Linux Celery live pilot saves **≥1** qualifying job (`live_api_verified`) with stable RSS, no OOM, no dump growth.
- Three consecutive **manual** `dispatch-once` pilots on Linux without `page_unresponsive` (operator discretion).
- Session refresh runbook tested.
- Prod index migration approved if using city-level targets.

## Approval gate

**No remote deploy or live run without operator message explicitly approving Contabo SSH changes.**