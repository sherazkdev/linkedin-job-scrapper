import { getPilotApiBase } from "@/lib/config";
import { getAlertBearer } from "@/lib/server/session";

export class PilotApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
  }
}

export async function pilotFetch(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<Response> {
  const url = `${getPilotApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init.headers);
  if (init.auth) {
    const token = await getAlertBearer();
    if (!token) throw new PilotApiError("Unauthorized", 401);
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(url, { ...init, headers, cache: "no-store" });
  return res;
}

export async function pilotJson<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const res = await pilotFetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new PilotApiError(
      (body as { detail?: string })?.detail ?? res.statusText,
      res.status,
      body,
    );
  }
  return body as T;
}