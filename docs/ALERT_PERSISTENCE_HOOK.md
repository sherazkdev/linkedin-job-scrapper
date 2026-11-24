# Alert persistence hook audit

## Path

`JobCollector` → `JobPersistenceService.persist_jobs` → `JobRepository.upsert_job_tracked` → optional `AlertProcessor.process_job_persisted` → `job_matches_saved_search` → `NotificationRepository.insert_in_app`.

## Wiring

`app/modules/collection/factory.py` → `_build_persistence()` attaches `AlertProcessor` **only when** `ALERTS_MATCHING_ENABLED=true`.

## Runtime flags (VPS)

| Service | `ALERTS_MATCHING_ENABLED` | Effect |
|---------|---------------------------|--------|
| Production `api` | `false` (default) | **No hook** — persist never calls `AlertProcessor` |
| Pilot `api-pilot` | `false` in compose overlay | Same unless explicitly enabled for UAT CLI |
| `worker-linkedin` | live collection off | No new persists from LinkedIn |

UAT used `app.cli.alerts_pilot_uat` with temporary env `ALERTS_MATCHING_ENABLED=true` inside the pilot container only — **not** the collection worker path.

## Reactivation dedupe

Event key `reactivated` + unique `(subscriber_id, event_key, job_id)` → one in-app notification per job per subscriber. See `tests/alerts/test_reactivation_dedupe.py`.

## Production notifications

`ALERTS_API_ENABLED=false` on production API — no registration or notification endpoints exposed.