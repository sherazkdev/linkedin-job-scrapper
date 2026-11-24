# Private frontend staging (VPS)

Loopback-only Next.js UI wired to **pilot API** (`global_jobs_pilot`). Not exposed on the production site domain.

## Deploy on VPS

```bash
cd /var/www/linkedin-job-scrapper
bash scripts/_vps_frontend_staging_deploy.sh
```

Compose overlay: `compose.contabo-frontend-staging.yaml` (port **127.0.0.1:13010**).

## Local access via SSH tunnel

```bash
ssh -L 13010:127.0.0.1:13010 -L 18097:127.0.0.1:18097 user@your-vps
```

Open http://localhost:13010 — set `APP_URL` to match the browser origin for CSRF (e.g. `http://127.0.0.1:13010`).

## Safety

- `PILOT_API_BASE_URL` / `PUBLIC_JOBS_API_BASE_URL` point at `api-pilot` only.
- Production alerts API remains disabled on `linkedin-scraper-api`.