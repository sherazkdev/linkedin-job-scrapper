import { NextResponse } from "next/server";

import { PilotApiError, readPilotJson } from "@/lib/server/pilot-fetch";

export function jsonError(message: string, status: number, extra?: Record<string, unknown>) {
  return NextResponse.json({ error: message, ...extra }, { status });
}

export function forbiddenCsrf() {
  return jsonError("Forbidden", 403);
}

export async function proxyPilotResponse(res: Response): Promise<NextResponse> {
  if (res.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  try {
    const body = await readPilotJson(res);
    return NextResponse.json(body, { status: res.status });
  } catch (e) {
    if (e instanceof PilotApiError) {
      return jsonError(e.message, e.status);
    }
    return jsonError("Upstream error", 502);
  }
}

export function handleBffError(e: unknown): NextResponse {
  if (e instanceof PilotApiError) {
    const status = e.status >= 400 && e.status < 600 ? e.status : 502;
    return jsonError(e.message, status);
  }
  return jsonError("Upstream error", 502);
}