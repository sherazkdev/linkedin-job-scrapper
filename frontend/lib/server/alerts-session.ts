import { pilotFetch, pilotJson, readPilotJson, PilotApiError } from "@/lib/server/pilot-fetch";
import { clearAlertSession, getAlertBearer, setAlertBearer } from "@/lib/server/session";

type RegisterOut = { subscriber_id: string; bearer_token: string };

type SavedSearchRow = { subscriber_id?: string };

export type SessionBootstrapResult =
  | { active: false }
  | { active: true; subscriber_id: string | null; created: boolean };

function subscriberIdFromSearches(body: unknown): string | null {
  const rows = body as SavedSearchRow[];
  if (!Array.isArray(rows) || rows.length === 0) return null;
  return rows[0]?.subscriber_id ?? null;
}

/** Returns whether the HttpOnly bearer is accepted by the pilot API. */
export async function validateExistingSession(): Promise<SessionBootstrapResult> {
  const token = await getAlertBearer();
  if (!token) return { active: false };

  try {
    const res = await pilotFetch("/api/v1/alerts/searches", { auth: true });
    if (res.status === 401) {
      await clearAlertSession();
      return { active: false };
    }
    if (!res.ok) {
      return { active: false };
    }
    const body = await readPilotJson(res);
    const subscriber_id = subscriberIdFromSearches(body);
    return { active: true, subscriber_id, created: false };
  } catch (e) {
    if (e instanceof PilotApiError && e.status === 401) {
      await clearAlertSession();
    }
    return { active: false };
  }
}

/** Idempotent: reuse valid cookie session or register once. Never replaces a valid session. */
export async function bootstrapAlertSession(): Promise<SessionBootstrapResult> {
  const existing = await validateExistingSession();
  if (existing.active) {
    return existing;
  }

  try {
    const out = await pilotJson<RegisterOut>("/api/v1/alerts/subscribers/register", {
      method: "POST",
    });
    await setAlertBearer(out.bearer_token);
    return { active: true, subscriber_id: out.subscriber_id, created: true };
  } catch (e) {
    if (e instanceof PilotApiError) throw e;
    throw new PilotApiError("Registration failed", 502);
  }
}