"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import type { JobItem, JobListResponse } from "@/lib/types/jobs";

export function JobSearchPanel({
  initial,
}: {
  initial: JobListResponse["data"] | null;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState(initial);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const fd = new FormData(e.currentTarget);
    const qs = new URLSearchParams();
    for (const [k, v] of fd.entries()) {
      if (typeof v === "string" && v.trim()) qs.set(k, v.trim());
    }
    qs.set("page", "1");
  qs.set("sort", "posted_at_desc");
    router.push(`/?${qs.toString()}`);
    try {
      const res = await fetch(`/api/jobs?${qs.toString()}`);
      const json = (await res.json()) as JobListResponse;
      if (!res.ok) throw new Error("Search failed");
      setData(json.data);
    } catch {
      setError("Could not load jobs. Check the API connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm">
          Keyword
          <input
            name="q"
            defaultValue={params.get("q") ?? ""}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            placeholder="e.g. Software Engineer"
          />
        </label>
        <label className="text-sm">
          Country
          <input
            name="country_code"
            defaultValue={params.get("country_code") ?? ""}
            maxLength={2}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 uppercase"
            placeholder="PK"
          />
        </label>
        <label className="text-sm">
          City <span className="text-slate-500">(structured field)</span>
          <input
            name="city"
            defaultValue={params.get("city") ?? ""}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm">
          Employment type
          <select name="employment_type" defaultValue={params.get("employment_type") ?? ""} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2">
            <option value="">Any</option>
            <option value="full_time">Full time</option>
            <option value="part_time">Part time</option>
            <option value="contract">Contract</option>
          </select>
        </label>
        <label className="text-sm">
          Remote
          <select name="is_remote" defaultValue={params.get("is_remote") ?? ""} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2">
            <option value="">Any</option>
            <option value="true">Remote only</option>
            <option value="false">On-site / hybrid</option>
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? "Searching…" : "Search jobs"}
          </button>
        </div>
      </form>
      <p className="text-xs text-slate-500">
        Listings respect the seven-day public visibility window on the API.
      </p>
      {error ? <p className="text-sm text-red-600" role="alert">{error}</p> : null}
      <JobResults data={data} />
    </div>
  );
}

function JobResults({ data }: { data: JobListResponse["data"] | null }) {
  if (!data) {
    return <p className="text-slate-600">Enter filters and search to see live pilot listings.</p>;
  }
  if (data.items.length === 0) {
    return <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-600">No jobs matched. Try broader filters or another country.</p>;
  }
  return (
    <section aria-live="polite">
      <p className="mb-3 text-sm text-slate-600">
        {data.total} results · page {data.page} of {data.total_pages}
      </p>
      <ul className="space-y-3">
        {data.items.map((job: JobItem) => (
          <li key={job.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <Link href={`/jobs/${job.id}`} className="font-medium text-slate-900 hover:underline">
                  {job.title}
                </Link>
                <p className="text-sm text-slate-600">{job.company}</p>
                <p className="text-xs text-slate-500">
                  {[job.city, job.country_code].filter(Boolean).join(", ") || job.location_text}
                </p>
              </div>
              {job.job_url ? (
                <a
                  href={job.job_url}
                  className="text-sm text-emerald-700 hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Original posting
                </a>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
