import { NextRequest, NextResponse } from "next/server";

import { getPublicJobsApiBase } from "@/lib/config";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  const url = `${getPublicJobsApiBase()}/api/v1/jobs/${encodeURIComponent(id)}`;
  const res = await fetch(url, { cache: "no-store" });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}