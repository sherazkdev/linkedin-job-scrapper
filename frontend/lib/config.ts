export function getPublicJobsApiBase(): string {
  return process.env.PUBLIC_JOBS_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:18097";
}

export function getPilotApiBase(): string {
  return process.env.PILOT_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:18097";
}

export function getAppUrl(): string {
  return process.env.APP_URL?.replace(/\/$/, "") ?? "http://localhost:3000";
}

export const ALERTS_SESSION_COOKIE =
  process.env.ALERTS_SESSION_COOKIE ?? "job_alerts_session";