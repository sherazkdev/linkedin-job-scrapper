# Operations runbook

## Health

| Check | Command |
|-------|---------|
| API liveness | `curl -s http://127.0.0.1:8085/health/live` |
| API readiness | `curl -s http://127.0.0.1:8085/health/ready` |
| Celery workers | `python -m app.cli.celery_ops ping` |
| Queue depth | `python -m app.cli.celery_ops stats` |

## Emergency stop (live LinkedIn)

1. `docker stop global-jobs-beat` (if running).
2. `docker stop global-jobs-worker-linkedin`.
3. Mongo: `db.collection_targets.updateMany({source:'linkedin'},{ $set: { enabled: false }})` on **test/pilot** DB only.
4. Confirm Redis queue empty: `LLEN collection`.

## Session attention

- `docker compose --profile collector run --rm collector python -m app.cli.linkedin_session status`
- Re-login host-side if expired; `install-docker` to refresh volume.

## Stale locks / orphaned runs

`python -m app.cli.collection_recover --mongo-db global_jobs_test`

## Logs

- Worker: `docker logs global-jobs-worker-linkedin --tail 200`
- Watch for `Chromium launched`, `search_nav`, `linkedin:js_probe_timeout` vs verification states.

## Backups

- Mongo: `mongodump` from mongodb container to off-host storage (operator schedule).
- Session volume: backup `storage_state.json` encrypted, not in git.

## Pilot target sync

`python -m app.cli.pilot_targets --mongo-db global_jobs_test` (defaults **disabled** in JSON).