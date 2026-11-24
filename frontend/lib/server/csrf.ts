import { headers } from "next/headers";

import { getAppUrl } from "@/lib/config";

/** Reject cross-site POSTs when APP_URL is configured. */
export async function assertSameOrigin(): Promise<void> {
  const h = await headers();
  const origin = h.get("origin");
  const app = getAppUrl();
  if (!origin) return;
  try {
    const o = new URL(origin);
    const a = new URL(app);
    if (o.host !== a.host) {
      throw new Error("Invalid origin");
    }
  } catch {
    throw new Error("Invalid origin");
  }
}