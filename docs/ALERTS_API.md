# Job alerts API (in-app channel)

Anonymous-device subscribers use server-issued bearer credentials. Tokens are shown **once** at registration and stored as SHA-256 hashes. If lost, register a new subscriber (saved searches cannot be recovered).

## Feature flags (env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `ALERTS_API_ENABLED` | `true` | Expose `/api/v1/alerts/*` |
| `ALERTS_MATCHING_ENABLED` | `false` | Match on job persist (off until rollout) |
| `ALERTS_DIGEST_ENABLED` | `false` | Allow manual `/digest/run` and Celery digest task |
| `ALERTS_PUSH_ENABLED` | `false` | Push provider (not configured) |
| `ALERTS_REGISTER_MAX_PER_IP` | `30` | Registrations per IP per hour (0=off) |

## City filter limitation

Saved-search `city` matches structured `job.city` only (same semantics as public jobs `city` filter). It does **not** search free-text `location_text`.

## Endpoints

All authenticated routes: `Authorization: Bearer <token>`.

### `POST /api/v1/alerts/subscribers/register`

Response:

```json
{
  "subscriber_id": "uuid",
  "bearer_token": "urlsafe-secret-once"
}
```

### Saved searches

- `GET /api/v1/alerts/searches`
- `POST /api/v1/alerts/searches` — body: `q`, `country_code`, `city`, `employment_type`, `is_remote`, `alerts_enabled`, digest fields
- `PATCH /api/v1/alerts/searches/{search_id}`
- `DELETE /api/v1/alerts/searches/{search_id}` → 204
- `POST /api/v1/alerts/searches/{search_id}/enable|disable`

### Notifications

- `GET /api/v1/alerts/notifications?page=1&page_size=20&unread_only=false`
- `GET /api/v1/alerts/notifications/unread-count`
- `POST /api/v1/alerts/notifications/mark-read` — `{ "notification_ids": ["..."] }` or `{ "mark_all": true }`
- `DELETE /api/v1/alerts/notifications/{notification_id}` → 204

### Daily digest (manual)

- `POST /api/v1/alerts/digest/run` — requires `ALERTS_DIGEST_ENABLED=true`

## MongoDB collections

- `alert_subscribers`, `saved_job_searches`, `alert_notifications`, `alert_digest_state`

Indexes ensured on API startup when `ALERTS_API_ENABLED=true`.