import { assertSameOrigin } from "@/lib/server/csrf";
import { forbiddenCsrf, handleBffError, proxyPilotResponse } from "@/lib/server/bff";
import { pilotFetch } from "@/lib/server/pilot-fetch";

type Params = { params: Promise<{ id: string }> };

export async function POST(_req: Request, { params }: Params) {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  const { id } = await params;
  try {
    const res = await pilotFetch(`/api/v1/alerts/searches/${encodeURIComponent(id)}/enable`, {
      method: "POST",
      auth: true,
    });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}