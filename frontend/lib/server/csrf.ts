import { headers } from "next/headers";

import { getAppUrl } from "@/lib/config";

export type TrustedRequestResult = { ok: true } | { ok: false; reason: string };

function normalizeOrigin(url: string): string | null {
  try {
    const u = new URL(url);
    const defaultPort = u.protocol === "https:" ? "443" : "80";
    const port = u.port || defaultPort;
    return `${u.protocol}//${u.hostname.toLowerCase()}:${port}`;
  } catch {
    return null;
  }
}

/** Compare browser Origin/Referer to configured APP_URL (never X-Forwarded-*). */
export function evaluateTrustedBrowserRequest(input: {
  appUrl: string;
  origin: string | null;
  referer: string | null;
  secFetchSite: string | null;
  method: string;
}): TrustedRequestResult {
  const trusted = normalizeOrigin(input.appUrl);
  if (!trusted) {
    return { ok: false, reason: "APP_URL misconfigured" };
  }

  const m = input.method.toUpperCase();
  if (m === "GET" || m === "HEAD") {
    return { ok: true };
  }

  if (input.secFetchSite === "cross-site") {
    return { ok: false, reason: "Cross-site request" };
  }

  if (input.origin) {
    const o = normalizeOrigin(input.origin);
    if (!o || o !== trusted) {
      return { ok: false, reason: "Origin mismatch" };
    }
    return { ok: true };
  }

  if (input.referer) {
    try {
      const r = new URL(input.referer);
      const refOrigin = normalizeOrigin(r.origin);
      if (refOrigin !== trusted) {
        return { ok: false, reason: "Referer mismatch" };
      }
      return { ok: true };
    } catch {
      return { ok: false, reason: "Invalid referer" };
    }
  }

  if (input.secFetchSite === "same-origin" || input.secFetchSite === "same-site") {
    return { ok: true };
  }

  return { ok: false, reason: "Missing origin" };
}

export async function assertSameOrigin(): Promise<void> {
  const h = await headers();
  const result = evaluateTrustedBrowserRequest({
    appUrl: getAppUrl(),
    origin: h.get("origin"),
    referer: h.get("referer"),
    secFetchSite: h.get("sec-fetch-site"),
    method: h.get("x-http-method-override") ?? "POST",
  });
  if (!result.ok) {
    throw new Error(result.reason);
  }
}