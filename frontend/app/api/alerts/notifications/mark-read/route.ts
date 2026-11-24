import { NextRequest, NextResponse } from "next/server";

import { assertSameOrigin } from "@/lib/server/csrf";
import { pilotFetch, PilotApiError } from "@/lib/server/pilot-fetch";

export async function POST(req: NextRequest) {
  try {
    await assertSameOrigin();
  } catch {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  try {
    const body = await req.json();
    const res = await pilotFetch("/api/v1/alerts/notifications/mark-read", {
      method: "POST",
      auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    if (e instanceof PilotApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: "Upstream error" }, { status: 502 });
  }
}