import { NextResponse } from "next/server";

import { assertSameOrigin } from "@/lib/server/csrf";
import { pilotJson } from "@/lib/server/pilot-fetch";
import { setAlertBearer } from "@/lib/server/session";

type RegisterOut = { subscriber_id: string; bearer_token: string };

export async function POST() {
  try {
    await assertSameOrigin();
  } catch {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  try {
    const out = await pilotJson<RegisterOut>("/api/v1/alerts/subscribers/register", {
      method: "POST",
    });
    await setAlertBearer(out.bearer_token);
    return NextResponse.json({ subscriber_id: out.subscriber_id });
  } catch (e: unknown) {
    const err = e as { status?: number; message?: string };
    return NextResponse.json(
      { error: err.message ?? "Registration failed" },
      { status: err.status ?? 502 },
    );
  }
}