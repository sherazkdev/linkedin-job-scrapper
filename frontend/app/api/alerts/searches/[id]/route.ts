import { NextRequest, NextResponse } from "next/server";

import { assertSameOrigin } from "@/lib/server/csrf";
import { pilotFetch, PilotApiError } from "@/lib/server/pilot-fetch";

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: NextRequest, { params }: Params) {
  try {
    await assertSameOrigin();
  } catch {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
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
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    if (e instanceof PilotApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: "Upstream error" }, { status: 502 });
  }
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  try {
    await assertSameOrigin();
  } catch {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const { id } = await params;
  try {
    const res = await pilotFetch(`/api/v1/alerts/searches/${encodeURIComponent(id)}`, {
      method: "DELETE",
      auth: true,
    });
    if (res.status === 204) return new NextResponse(null, { status: 204 });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    if (e instanceof PilotApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: "Upstream error" }, { status: 502 });
  }
}