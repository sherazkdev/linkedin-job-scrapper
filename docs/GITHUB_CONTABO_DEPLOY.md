# GitHub → Contabo deployment (isolated stack)

Deploy path on VPS: **`/var/www/linkedin-job-scrapper`**  
Compose project: **`linkedin-scraper`** (isolated Mongo, Redis, volumes, bridge network)  
**Defaults:** Celery Beat **off**, live LinkedIn **off** — enable only per runbooks after pilot sign-off.

---

## 1. Preflight on VPS (read-only)

```bash
uname -a && free -h && df -h
docker version && docker compose version

# Port / name clashes with your ~20 apps (Mongo/Redis have no host ports in this stack)
docker ps -a --format 'table {{.Names}}\t{{.Ports}}' | grep -E '18095|18096|linkedin-scraper|global-jobs' || true
ss -tlnp | grep -E ':18095|:18096|:8085|:18085' || echo "loopback API ports likely free"

# Confirm target paths
test -d /var/www || sudo mkdir -p /var/www
```

Adjust `LINKEDIN_SCRAPER_API_PORT` / `LINKEDIN_SCRAPER_API_TEST_PORT` in `.env` if `18095`/`18096` are taken.

---

## 2. First-time VPS setup

```bash
sudo mkdir -p /var/www/linkedin-job-scrapper
sudo chown "$USER:$USER" /var/www/linkedin-job-scrapper
cd /var/www/linkedin-job-scrapper

# After you configure a private Git remote locally — first push from dev machine, then:
git clone git@github.com:YOUR_ORG/linkedin-job-scrapper.git .
# OR: git pull origin main

cp .env.example .env
nano .env   # set strong MONGO_ROOT_PASSWORD, REDIS_PASSWORD, MONGO_URI, REDIS_URL, MONGO_DB_NAME
```

**`.env` on VPS (minimal production base):**

- `MONGO_DB_NAME=global_jobs` (or `global_jobs_pilot` for pilot phase)
- `ALLOW_LIVE_LINKEDIN_COLLECTION=false`
- `CELERY_ALLOW_LINKEDIN_TASKS=false`
- `ALLOW_COLLECTION_PRODUCTION_DB=false` until cutover approved
- Optional: `LINKEDIN_SCRAPER_API_PORT=18095` (see `compose.contabo-vps.yaml`)

LinkedIn session (once, not in git):

```bash
# Create volume-backed session without printing cookies
docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper up -d mongodb redis
# Copy storage_state.json into volume (example — adjust host path):
docker run --rm -v linkedin_scraper_linkedin_auth:/data/linkedin -v /secure/path:/in:ro \
  alpine cp /in/storage_state.json /data/linkedin/storage_state.json
chmod 600 on host source file; remove from /tmp after copy.
```

---

## 3. Build and start (safe default — no Beat, no live worker)

**Merged config files:** `compose.yaml` + `compose.contabo-vps.yaml`  
**Optional pilot DB overlay:** add `compose.contabo-pilot.yaml`

```bash
cd /var/www/linkedin-job-scrapper

docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper config -q

docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper build api

docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper up -d mongodb redis api
```

Health:

```bash
curl -sf http://127.0.0.1:18095/health/live
curl -sf http://127.0.0.1:18095/health/ready
```

Nginx (existing vhost) — example:

```nginx
location /linkedin-jobs/ {
    proxy_pass http://127.0.0.1:18095/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

## 4. Pilot worker (still live=false in compose; profile only)

```bash
docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper \
  --profile celery-linkedin up -d worker-linkedin

# Do NOT start beat:
# docker compose ... --profile celery up -d beat   # forbidden until pilot PASS
```

One-shot live collect: follow `docs/CONTABO_LINUX_PILOT.md` (temporary env override on worker, single `dispatch-once`).

---

## 5. GitHub update flow (routine deploy)

**On development machine (after tests):**

```bash
git status   # ensure .env not listed
git push origin main
```

**On VPS:**

```bash
cd /var/www/linkedin-job-scrapper
git fetch origin
git log -1 --oneline origin/main
git pull --ff-only origin main

docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper config -q
docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper build api
docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper up -d mongodb redis api

# If worker image changed:
docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper \
  --profile celery-linkedin build worker-linkedin
docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper \
  --profile celery-linkedin up -d worker-linkedin
```

---

## 6. Rollback

**Application rollback (keep data volumes):**

```bash
cd /var/www/linkedin-job-scrapper
git fetch origin
git checkout <previous-known-good-sha>
docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper build api
docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper up -d mongodb redis api
```

**Emergency stop (no volume delete):**

```bash
docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper \
  --profile celery-linkedin stop
docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper stop
```

**Never run** `docker compose down -v` on production/pilot without explicit approval — destroys `linkedin_scraper_*` volumes.

---

## 7. Conflict audit (shared VPS)

| Resource | Default local dev | This VPS overlay |
|----------|-------------------|------------------|
| Compose project | `linkedin-job-scrapper` dir name | `-p linkedin-scraper` |
| Containers | `global-jobs-*` | `linkedin-scraper-*` |
| Volumes | `global_jobs_*` | `linkedin_scraper_*` |
| Network | `…_internal` | `linkedin_scraper_internal` |
| API (prod) | `127.0.0.1:8085` | `127.0.0.1:18095` (env override) |
| API (test) | `127.0.0.1:18085` | `127.0.0.1:18096` |
| Mongo / Redis host ports | **none** | **none** (internal bridge only) |
| Beat | profile `celery` | **not started by default** |
| Live LinkedIn | `false` in compose | `false`; pilot overlay unchanged |

If another app already uses `global-jobs-api` on the same host, the VPS overlay avoids that conflict.

---

## 8. Local: initialize git and first commit (Windows dev)

```powershell
cd E:\linkedin-job-scrapper
git init
git check-ignore -v .env
git add .
git status   # verify .env, .venv, data/ are NOT staged
git commit -m "chore: initial release for Contabo isolated deployment"
# After creating private GitHub repo:
# git remote add origin git@github.com:YOUR_ORG/linkedin-job-scrapper.git
# git push -u origin main
```