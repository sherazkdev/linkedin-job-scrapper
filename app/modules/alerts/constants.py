"""MongoDB collection names for job alerts."""

ALERT_SUBSCRIBERS = "alert_subscribers"
SAVED_JOB_SEARCHES = "saved_job_searches"
ALERT_NOTIFICATIONS = "alert_notifications"
ALERT_DIGEST_STATE = "alert_digest_state"

EVENT_NEW_JOB = "new_job"
EVENT_JOB_UPDATED = "job_updated"
EVENT_REACTIVATED = "reactivated"
EVENT_DIGEST = "daily_digest"
EVENT_DIGEST_PREVIEW = "daily_digest_preview"

# Mongo collection for atomic digest idempotency (subscriber + local date key)
ALERT_DIGEST_DELIVERIES = "alert_digest_deliveries"

TEST_SUBSCRIBER_TAG = "integration_test"