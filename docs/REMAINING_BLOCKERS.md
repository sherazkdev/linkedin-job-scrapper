# Remaining blockers

1. **Live Celery + Playwright on native Linux** — not proven (`js_probe_timeout` / `page_unresponsive` on WSL Celery; manual CLI succeeded).
2. **G9–G11 acceptance** — require Contabo evidence (≥1 job saved via Celery, stability runs, capacity sign-off).
3. **Production `collection_targets` index migration** — `ALLOW_COLLECTION_TARGET_INDEX_MIGRATION` must not run on prod without backup + approval.
4. **Active run de-duplication by city** — `collection_runs` RUNNING guard is keyword-only; parallel city targets need schema follow-up.
5. **Windows/WSL** — not a supported runtime for live LinkedIn scheduling (Chromium crash dumps).
6. **Beat worldwide scheduling** — intentionally **disabled** until Linux pilot passes.

## Clear next action

Approve **isolated Contabo pilot** (separate Compose project `linkedin-pilot`) and run **one** `dispatch-once` with live flags on `worker-linkedin` only — per `CONTABO_LINUX_PILOT.md`.