export type AlertSessionState = {
  active: boolean;
  subscriber_id?: string | null;
  created?: boolean;
};

export async function fetchAlertSession(): Promise<AlertSessionState> {
  const res = await fetch("/api/alerts/session", { credentials: "same-origin" });
  const data = (await res.json()) as AlertSessionState & { error?: string };
  if (!res.ok) {
    throw new Error(data.error ?? "Session check failed");
  }
  return data;
}

/** Idempotent: creates a session only when none is valid. */
export async function ensureAlertSession(): Promise<AlertSessionState> {
  const current = await fetchAlertSession();
  if (current.active) return current;
  const res = await fetch("/api/alerts/session", {
    method: "POST",
    credentials: "same-origin",
  });
  const data = (await res.json()) as AlertSessionState & { error?: string };
  if (!res.ok) {
    throw new Error(data.error ?? "Could not start alert session");
  }
  return data;
}

export async function logoutAlertSession(): Promise<void> {
  await fetch("/api/alerts/session", {
    method: "DELETE",
    credentials: "same-origin",
  });
}