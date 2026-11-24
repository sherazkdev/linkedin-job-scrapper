import { handleBffError, proxyPilotResponse } from "@/lib/server/bff";
import { pilotFetch } from "@/lib/server/pilot-fetch";

export async function GET() {
  try {
    const res = await pilotFetch("/api/v1/alerts/notifications/unread-count", { auth: true });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}