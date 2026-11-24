import { cookies } from "next/headers";

import { ALERTS_SESSION_COOKIE } from "@/lib/config";

export async function getAlertBearer(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(ALERTS_SESSION_COOKIE)?.value ?? null;
}

export async function setAlertBearer(token: string): Promise<void> {
  const jar = await cookies();
  jar.set(ALERTS_SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/alerts",
    maxAge: 60 * 60 * 24 * 365,
  });
}

export async function clearAlertSession(): Promise<void> {
  const jar = await cookies();
  jar.delete(ALERTS_SESSION_COOKIE);
}