# Contabo Ubuntu VPS — deployment preflight

**Do not deploy until all blockers are cleared.** No credentials below — use your secrets manager.

## 1. Host assumptions

| Item | Recommendation |
|------|----------------|
| OS | Ubuntu 22.04/24.04 LTS |
| vCPU / RAM | 2 vCPU / 4 GB minimum (Playwright collector profile adds 2+ GB if enabled) |
| Disk | 40 GB+; Mongo volume growth for job text |
| Public ports | **443** (proxy), **22** (SSH, key-only) only |
| App bind | API on `127.0.0.1` behind nginx/caddy |

## 2. Firewall (ufw example)

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw allow 443/tcp
sudo ufw enable
```

Do **not** expose `27017` (Mongo) or `6379` (Redis).

## 3. Required environment variables

Copy `.env.example` → `.env` and set:

- `APP_ENV=production`
- `MONGO_ROOT_USER`, `MONGO_ROOT_PASSWORD`, `MONGO_URI`, `MONGO_DB_NAME=global_jobs`
- `REDIS_PASSWORD`, `REDIS_URL`
- `API_CORS_ORIGINS` (Flutter origins, comma-separated)
- `INTERNAL_OPS_TOKEN` (long random; monitoring only)
- `ALLOW_COLLECTION_PRODUCTION_DB=false` until ops process approved
- `ALLOW_LIVE_LINKEDIN_COLLECTION=false`
- `ALLOW_LIVE_PUBLIC_BOARD_COLLECTION=false`
- `CELERY_ALLOW_LINKEDIN_TASKS=false`
- `CELERY_WORKER_MONGO_DB_NAME=global_jobs` (or dedicated worker DB policy)
- `JOBS_MAX_PAGE=500`

## 4. Compose on VPS

```bash
cd /opt/global-jobs
docker compose up -d api mongodb redis
docker compose --profile celery up -d worker beat   # if scheduling needed
```

Remove or keep `ports: 127.0.0.1:8085:8000` — proxy terminates TLS and forwards to `127.0.0.1:8085`.

## 5. Reverse proxy (sketch)

- TLS certificate (Let's Encrypt)
- `proxy_read_timeout 60s`
- Rate limit: e.g. `limit_req_zone` 10r/s per IP on `/api/`
- HSTS at proxy layer

## 6. MongoDB backup

**Safety:** default target `global_jobs`; confirm db name before any command.

```bash
# Backup (run from host with docker access)
docker compose exec mongodb mongodump \
  --username="$MONGO_ROOT_USER" --password="$MONGO_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --db global_jobs \
  --out /data/backup/$(date +%Y%m%dT%H%M%SZ)

docker cp global-jobs-mongodb:/data/backup ./backups/
```

- Store off-server (encrypted object storage)
- Exclude `linkedin_auth` volume secrets from public archives

## 7. Restore rehearsal (isolated DB only)

```bash
# Create NEW database name — never overwrite global_jobs in rehearsal
docker compose exec mongodb mongorestore \
  --username="$MONGO_ROOT_USER" --password="$MONGO_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --db global_jobs_restore_test \
  /data/backup/<timestamp>/global_jobs
```

Checkpoint: verify document counts match backup manifest before any production restore.

## 8. Rollback

1. Stop API: `docker compose stop api`
2. Deploy previous image tag / git commit build
3. `docker compose up -d api`
4. If bad migration: restore from last known-good backup to **new** DB, switch `MONGO_DB_NAME` only after validation

## 9. Production migration checkpoints

- Run `migrate_jobs_schema` **dry-run** on staging clone first
- Never auto-backfill `country_code` from search market
- Reindex via app startup (`ensure_job_indexes`) — idempotent

## 10. Deployment blockers

- [ ] Legal sign-off on job data redistribution model
- [ ] Secrets rotated from development placeholders
- [ ] CORS and TLS configured
- [ ] Backups scheduled + restore tested on `global_jobs_restore_test`
- [ ] LinkedIn remains disabled until separate compliance review
- [ ] Public board collection remains CLI-gated (not Beat)

## 11. Post-deploy smoke

```bash
curl -sf https://jobs.example.com/health/ready
curl -sf "https://jobs.example.com/api/v1/jobs?page_size=1"
```

Use test DB verification pattern from `docs/PHASE_3B_2.md` before pointing mobile app at production.