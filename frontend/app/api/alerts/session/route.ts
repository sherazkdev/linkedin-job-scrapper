import { NextResponse } from "next/server";

import { bootstrapAlertSession, validateExistingSession } from "@/lib/server/alerts-session";
import { forbiddenCsrf, handleBffError } from "@/lib/server/bff";
import { assertSameOrigin } from "@/lib/server/csrf";
import { clearAlertSession } from "@/lib/server/session";

export async function GET() {
  try {
    const state = await validateExistingSession();
    if (!state.active) {
      return NextResponse.json({ active: false });
    }
    return NextResponse.json({
      active: true,
      subscriber_id: state.subscriber_id,
      created: false,
    });
  } catch (e) {
    return handleBffError(e);
  }
}

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
      active: true,
      subscriber_id: state.subscriber_id,
      created: state.created ?? false,
    });
  } catch (e) {
    return handleBffError(e);
  }
}

export async function DELETE() {
  try {
    await assertSameOrigin();
  } catch {
    return forbiddenCsrf();
  }
  await clearAlertSession();
  return NextResponse.json({ active: false });
}