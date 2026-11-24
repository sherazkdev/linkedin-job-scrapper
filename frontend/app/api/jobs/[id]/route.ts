import { NextRequest } from "next/server";

import { getPublicJobsApiBase } from "@/lib/config";
import { jsonError } from "@/lib/server/bff";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  const url = `${getPublicJobsApiBase()}/api/v1/jobs/${encodeURIComponent(id)}`;
  try {
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(15_000) });
    const text = await res.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      return jsonError("Invalid response", 502);
    }
    if (!res.ok) {
      const body = data as { detail?: string };
      return jsonError(body.detail ?? "Not found", res.status === 404 ? 404 : res.status);
    }
    return Response.json(data, { status: res.status });
  } catch {
    return jsonError("Jobs API unavailable", 503);
  }
}