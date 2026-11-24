import { cookies } from "next/headers";

import { getAppUrl, ALERTS_SESSION_COOKIE } from "@/lib/config";

function cookieSecure(): boolean {
  if (process.env.COOKIE_SECURE === "true") return true;
  if (process.env.COOKIE_SECURE === "false") return false;
  try {
    return new URL(getAppUrl()).protocol === "https:";
  } catch {
    return process.env.NODE_ENV === "production";
  }
}

export async function getAlertBearer(): Promise<string | null> {
  const jar = await cookies();
  const raw = jar.get(ALERTS_SESSION_COOKIE)?.value;
  return raw?.trim() ? raw : null;
}

export async function setAlertBearer(token: string): Promise<void> {
  const jar = await cookies();
  jar.set(ALERTS_SESSION_COOKIE, token, {
    httpOnly: true,
    secure: cookieSecure(),
    sameSite: "lax",
    path: "/api/alerts",
    maxAge: 60 * 60 * 24 * 365,
  });
}

export async function clearAlertSession(): Promise<void> {
  const jar = await cookies();
  jar.set(ALERTS_SESSION_COOKIE, "", {
    httpOnly: true,
    secure: cookieSecure(),
    sameSite: "lax",
    path: "/api/alerts",
    maxAge: 0,
  });
}