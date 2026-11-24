import { NextRequest, NextResponse } from "next/server";

import { pilotFetch, PilotApiError } from "@/lib/server/pilot-fetch";

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.searchParams.toString();
  try {
    const res = await pilotFetch(
      `/api/v1/alerts/notifications${qs ? `?${qs}` : ""}`,
      { auth: true },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    if (e instanceof PilotApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: "Upstream error" }, { status: 502 });
  }
}