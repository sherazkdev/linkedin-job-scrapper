import { NextRequest } from "next/server";

import { assertSameOrigin } from "@/lib/server/csrf";
import { forbiddenCsrf, handleBffError, proxyPilotResponse } from "@/lib/server/bff";
import { pilotFetch } from "@/lib/server/pilot-fetch";

export async function GET() {
  try {
    const res = await pilotFetch("/api/v1/alerts/searches", { auth: true });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}

export async function POST(req: NextRequest) {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  try {
    const body = await req.json();
    const res = await pilotFetch("/api/v1/alerts/searches", {
      method: "POST",
      auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}