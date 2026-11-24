import { NextRequest } from "next/server";

import { handleBffError, proxyPilotResponse } from "@/lib/server/bff";
import { pilotFetch } from "@/lib/server/pilot-fetch";

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.searchParams.toString();
  try {
    const res = await pilotFetch(
      `/api/v1/alerts/notifications${qs ? `?${qs}` : ""}`,
      { auth: true },
    );
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}