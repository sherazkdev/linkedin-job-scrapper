import { getPilotApiBase } from "@/lib/config";
import { getAlertBearer } from "@/lib/server/session";

const DEFAULT_TIMEOUT_MS = 15_000;

export class PilotApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
  }
}

function safeDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const b = body as Record<string, unknown>;
  if (typeof b.detail === "string") return b.detail;
  if (Array.isArray(b.detail)) return b.detail.map(String).join("; ");
  if (typeof b.error === "string") return b.error;
  return fallback;
}

export async function pilotFetch(
  path: string,
  init: RequestInit & { auth?: boolean; timeoutMs?: number } = {},
): Promise<Response> {
  const url = `${getPilotApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init.headers);
  if (init.auth) {
    const token = await getAlertBearer();
    if (!token) throw new PilotApiError("Unauthorized", 401);
    headers.set("Authorization", `Bearer ${token}`);
  }
  const timeoutMs = init.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    if (msg.includes("aborted") || msg.includes("timeout")) {
      throw new PilotApiError("Upstream timeout", 504);
    }
    throw new PilotApiError("Pilot API unavailable", 503);
  }
  return res;
}

export async function readPilotJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new PilotApiError("Invalid upstream response", 502);
  }
}

export async function pilotJson<T>(
  path: string,
  init: RequestInit & { auth?: boolean; timeoutMs?: number } = {},
): Promise<T> {
  const res = await pilotFetch(path, init);
  const body = await readPilotJson(res);
  if (!res.ok) {
    throw new PilotApiError(safeDetail(body, res.statusText || "Request failed"), res.status, body);
  }
  return body as T;
}