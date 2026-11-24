# Future production HTTPS (not enabled)

Staging remains **127.0.0.1:13010** (SSH tunnel only). This documents a future public cutover.

## Intended hostname

Example: `jobs.example.com` (placeholder — not wired in Nginx yet).

## TLS

- Let's Encrypt via certbot, or uploaded certs
- Terminate TLS at Nginx; proxy to loopback `frontend-staging` or dedicated prod UI container

## Application env

| Variable | HTTPS value |
|----------|-------------|
| `APP_URL` | `https://jobs.example.com` |
| `COOKIE_SECURE` | `true` |
| `PILOT_API_BASE_URL` | internal Docker URL only (never browser-exposed) |

## Reverse proxy (sketch)

```nginx
server {
  listen 443 ssl http2;
  server_name jobs.example.com;
  # ssl_certificate ...
  add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'none';" always;
  add_header X-Frame-Options "DENY" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  # Do NOT forward untrusted X-Forwarded-Host into Next.js CSRF logic
  proxy_pass http://127.0.0.1:13010;
}
```

## Health & rollback

- `GET /api/health` returns `git_sha` for deploy verification
- Keep `linkedin-scraper-frontend-staging:rollback-<sha>` tags from deploy script
- Rollback: retag rollback image as `latest` and `compose up -d frontend-staging`