# Security audit — git and deployment secrets

**Audit date:** 2026-11-16  
**Scope:** Repository root, `.gitignore`, `.dockerignore`, Compose overlays, tracked source.

## Result: **PASS** (after hardening)

| Check | Status | Notes |
|-------|--------|--------|
| `.env` excluded | **PASS** | Listed in `.gitignore`; use `.env.example` only |
| LinkedIn `storage_state.json` | **PASS** | `data/`, `**/storage_state.json` ignored |
| Browser / Playwright artifacts | **PASS** | `.playwright/`, profiles, `WSLCrash/` ignored |
| Mongo dumps / BSON | **PASS** | `*.bson`, `dump/`, `mongo-backup/` ignored |
| Logs and temp scripts | **PASS** | `*.log`, `.tmp*` ignored; ad-hoc `.tmp_pilot_prep.js` removed |
| Docker build context | **PASS** | `.dockerignore` excludes `.env`, `data/`, session JSON |
| Hardcoded production passwords in repo | **PASS** | Only `change_me_*` placeholders in `.env.example` and test defaults |
| Session in compose | **PASS** | Volume mount path only; no cookie payload in YAML |
| `config/linkedin_pilot_targets.json` | **PASS** | Targets only — no credentials |
| Beat / live LinkedIn default | **PASS** | `ALLOW_LIVE_LINKEDIN_COLLECTION=false`, `CELERY_ALLOW_LINKEDIN_TASKS=false`; Beat behind `celery` profile |

## Operator responsibilities (not enforced by git)

1. Generate unique `MONGO_ROOT_PASSWORD`, `REDIS_PASSWORD`, and `INTERNAL_OPS_TOKEN` on the VPS — never reuse from other apps.
2. Copy `storage_state.json` via `scp`/volume mount; **never** `git add` session files.
3. Use private GitHub (or self-hosted) remote; verify `git check-ignore -v .env` before first push.
4. Run pre-push: `git status` must not list `.env`, `data/`, or `*.pem`.

## Verification commands (local or CI)

```bash
git check-ignore -v .env data/linkedin/storage_state.json .venv __pycache__
git ls-files | grep -E '\.env$|storage_state|\.pem$|\.bson$' && echo FAIL || echo OK
```