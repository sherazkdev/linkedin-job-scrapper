import { NextResponse } from "next/server";

import { bootstrapAlertSession } from "@/lib/server/alerts-session";
import { forbiddenCsrf, handleBffError } from "@/lib/server/bff";
import { assertSameOrigin } from "@/lib/server/csrf";

/** Idempotent alias for POST /api/alerts/session (backward compatible path). */
export async function POST() {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  try {
    const state = await bootstrapAlertSession();
    if (!state.active) {
      return NextResponse.json({ error: "Session unavailable" }, { status: 503 });
    }
    return NextResponse.json({
      subscriber_id: state.subscriber_id,
      reused: !state.created,
    });
  } catch (e) {
    return handleBffError(e);
  }
}