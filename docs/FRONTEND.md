# Job Finder frontend (Next.js)

## Architecture

- `frontend/` — Next.js App Router, TypeScript, Tailwind
- **BFF** under `app/api/*` proxies the pilot API; browser never sees bearer tokens
- Idempotent `POST /api/alerts/session` (reuses valid HttpOnly cookie; register only when needed)
- HttpOnly cookie `job_alerts_session` (path `/api/alerts`) stores the pilot bearer server-side
- `DELETE /api/alerts/session` clears the alert session (sign out)
- Public job search uses `PUBLIC_JOBS_API_BASE_URL` (pilot in dev)

## Routes

| Page | Path |
|------|------|
| Home / search | `/` |
| Job detail | `/jobs/[id]` |
| Saved searches | `/saved-searches` |
| Notifications | `/notifications` |
| Digest preferences | `/preferences` |

## Local preview

```bash
# SSH tunnel to VPS pilot API (example)
ssh -L 18097:127.0.0.1:18097 user@vps

cd frontend
cp .env.example .env.local
# set PUBLIC_JOBS_API_BASE_URL and PILOT_API_BASE_URL to http://127.0.0.1:18097

npm install
npm run dev
```

Open http://localhost:3000

## Tests

```bash
cd frontend
npm run test
npm run build
```

## Deployment

Not wired to production domain in this phase. Host as a separate Node service or static export behind your reverse proxy when ready.