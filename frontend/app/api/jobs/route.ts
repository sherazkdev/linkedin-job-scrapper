import { NextRequest, NextResponse } from "next/server";

import { getPublicJobsApiBase } from "@/lib/config";

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.searchParams.toString();
  const url = `${getPublicJobsApiBase()}/api/v1/jobs${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}