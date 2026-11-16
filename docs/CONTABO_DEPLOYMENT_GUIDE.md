# Contabo deployment guide (isolated pilot → production cutover)

**Do not** attach to existing production Docker volumes, Nginx vhosts, or MongoDB instances on the VPS without a migration plan.

## Prerequisites

| Resource | Minimum (pilot) |
|----------|-----------------|
| RAM | 4 GB host free (worker `mem_limit: 2g`) |
| Disk | 20 GB free + monitor crash dumps |
| OS | Native **Linux** (not WSL) |
| Access | SSH as deploy user; secrets **not** in git |

## Isolated pilot Compose

```bash
cd /var/www/linkedin-job-scrapper   # isolated directory from other apps (see GITHUB_CONTABO_DEPLOY.md)
git clone <private-repo-url> .
cp .env.example .env    # fill MONGO_URI, REDIS, passwords locally
docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper \
  --profile celery-linkedin up -d mongodb redis api worker-linkedin
```

- **Do not** start `beat` for first live attempt.
- Session: copy `storage_state.json` into pilot `linkedin_auth` volume (see `docs/LINKEDIN_COLLECTION.md`).
- DB: `CELERY_WORKER_MONGO_DB_NAME=global_jobs_pilot` (pilot overlay).

## One-shot live collect (operator)

1. Confirm session cookie count without printing values: `linkedin_session status` in collector container.
2. Enable **one** `collection_targets` row; set `enabled=true`, `max_jobs_per_run=1`.
3. Start temporary worker with live env **only** for that run (see `CONTABO_LINUX_PILOT.md`).
4. `python -m app.cli.celery_ops dispatch-once` once.
5. Disable target; stop live worker.

## API behind existing Nginx

- Bind API to `127.0.0.1:18085` (test) or internal Docker network.
- Nginx `proxy_pass` to container; TLS terminates at Nginx.
- **Do not** publish MongoDB/Redis ports publicly.

## Production cutover (after G9–G11 PASS)

Separate Compose project `global-jobs-prod`, distinct volumes, `MONGO_DB_NAME=global_jobs`, Beat enabled only after pilot sign-off.

## Rollback

```bash
docker compose -p linkedin-pilot stop
# data preserved on named volumes; no down -v unless operator approves
```