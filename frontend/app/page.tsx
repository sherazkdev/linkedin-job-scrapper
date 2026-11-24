import { Suspense } from "react";

import { JobSearchPanel } from "@/features/jobs/JobSearchPanel";
import { getPublicJobsApiBase } from "@/lib/config";
import type { JobListResponse } from "@/lib/types/jobs";

async function loadInitial(searchParams: Record<string, string | string[] | undefined>) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(searchParams)) {
    if (typeof v === "string" && v) qs.set(k, v);
  }
  if (!qs.has("page")) qs.set("page", "1");
  qs.set("sort", "posted_at_desc");
  if ([...qs.keys()].filter((k) => k !== "page" && k !== "sort").length === 0) {
    return null;
  }
  try {
    const res = await fetch(`${getPublicJobsApiBase()}/api/v1/jobs?${qs}`, { cache: "no-store" });
    const json = (await res.json()) as JobListResponse;
    return json.data;
  } catch {
    return null;
  }
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const initial = await loadInitial(sp);
  return (
    <div>
      <h1 className="mb-2 text-2xl font-semibold">Job search</h1>
      <p className="mb-6 text-slate-600">Live listings from the pilot API (last seven days).</p>
      <Suspense fallback={<p>Loading search…</p>}>
        <JobSearchPanel initial={initial} />
      </Suspense>
    </div>
  );
}