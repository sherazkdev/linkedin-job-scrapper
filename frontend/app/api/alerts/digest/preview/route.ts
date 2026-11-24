import { assertSameOrigin } from "@/lib/server/csrf";
import { forbiddenCsrf, handleBffError, proxyPilotResponse } from "@/lib/server/bff";
import { pilotFetch } from "@/lib/server/pilot-fetch";

export async function POST() {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  try {
    const res = await pilotFetch("/api/v1/alerts/digest/preview", {
      method: "POST",
      auth: true,
    });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}