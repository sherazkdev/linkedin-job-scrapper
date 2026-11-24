import { NextRequest } from "next/server";

import { assertSameOrigin } from "@/lib/server/csrf";
import { forbiddenCsrf, handleBffError, proxyPilotResponse } from "@/lib/server/bff";
import { pilotFetch } from "@/lib/server/pilot-fetch";

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: NextRequest, { params }: Params) {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  const { id } = await params;
  try {
    const body = await req.json();
    const res = await pilotFetch(`/api/v1/alerts/searches/${encodeURIComponent(id)}`, {
      method: "PATCH",
      auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  const { id } = await params;
  try {
    const res = await pilotFetch(`/api/v1/alerts/searches/${encodeURIComponent(id)}`, {
      method: "DELETE",
      auth: true,
    });
    return proxyPilotResponse(res);
  } catch (e) {
    return handleBffError(e);
  }
}