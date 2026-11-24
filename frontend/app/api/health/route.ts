import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    ok: true,
    git_sha: process.env.GIT_COMMIT_SHA ?? "unknown",
    node_env: process.env.NODE_ENV ?? "unknown",
  });
}