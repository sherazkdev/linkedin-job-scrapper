import { NextRequest } from "next/server";

import { getPublicJobsApiBase } from "@/lib/config";
import { jsonError } from "@/lib/server/bff";

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.searchParams.toString();
  const url = `${getPublicJobsApiBase()}/api/v1/jobs${qs ? `?${qs}` : ""}`;
  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(15_000) });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    if (msg.includes("timeout")) return jsonError("Jobs API timeout", 504);
    return jsonError("Jobs API unavailable", 503);
  }
  const text = await res.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    return jsonError("Invalid jobs API response", 502);
  }
  if (!res.ok) {
    const body = data as { detail?: string };
    return jsonError(body.detail ?? "Search failed", res.status);
  }
  return Response.json(data, { status: res.status });
}