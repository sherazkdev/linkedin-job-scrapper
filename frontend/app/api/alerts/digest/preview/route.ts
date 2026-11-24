import { NextResponse } from "next/server";

import { assertSameOrigin } from "@/lib/server/csrf";
import { pilotFetch, PilotApiError } from "@/lib/server/pilot-fetch";

export async function POST() {
  try {
    await assertSameOrigin();
  } catch {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  try {
    const res = await pilotFetch("/api/v1/alerts/digest/preview", {
      method: "POST",
      auth: true,
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