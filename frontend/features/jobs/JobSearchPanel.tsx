"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

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

  const fetchJobs = useCallback(
    async (qs: URLSearchParams) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/jobs?${qs.toString()}`);
        const json = (await res.json()) as JobListResponse & { error?: string };
        if (!res.ok) throw new Error(json.error ?? "Search failed");
        setData(json.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load jobs");
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    const qs = new URLSearchParams(params.toString());
    if (!qs.has("page")) qs.set("page", "1");
    if (!qs.has("sort")) qs.set("sort", "posted_at_desc");
    const hasFilters = [...qs.keys()].some((k) => k !== "page" && k !== "sort");
    if (hasFilters) {
      void fetchJobs(qs);
    }
  }, [params, fetchJobs]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const qs = new URLSearchParams();
    for (const [k, v] of fd.entries()) {
      if (typeof v === "string" && v.trim()) qs.set(k, v.trim());
    }
    qs.set("page", "1");
    qs.set("sort", "posted_at_desc");
    router.push(`/?${qs.toString()}`);
  }

  function goToPage(page: number) {
    const qs = new URLSearchParams(params.toString());
    qs.set("page", String(page));
    if (!qs.has("sort")) qs.set("sort", "posted_at_desc");
    router.push(`/?${qs.toString()}`);
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={onSubmit}
        className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-3"
      >
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
          <select
            name="employment_type"
            defaultValue={params.get("employment_type") ?? ""}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          >
            <option value="">Any</option>
            <option value="full_time">Full time</option>
            <option value="part_time">Part time</option>
            <option value="contract">Contract</option>
          </select>
        </label>
        <label className="text-sm">
          Remote
          <select
            name="is_remote"
            defaultValue={params.get("is_remote") ?? ""}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          >
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
        Listings respect the seven-day public visibility window on the API. Sort: newest first.
      </p>
      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      {loading && !data ? <p className="text-slate-600">Loading results…</p> : null}
      <JobResults data={data} loading={loading} onPageChange={goToPage} />
    </div>
  );
}

function JobResults({
  data,
  loading,
  onPageChange,
}: {
  data: JobListResponse["data"] | null;
  loading: boolean;
  onPageChange: (page: number) => void;
}) {
  if (!data) {
    return (
      <p className="text-slate-600">Enter filters and search to see live pilot listings.</p>
    );
  }
  if (data.items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-600">
        No jobs matched. Try broader filters or another country.
      </p>
    );
  }
  const canPrev = data.page > 1;
  const canNext = data.page < data.total_pages;
  return (
    <section aria-live="polite">
      <p className="mb-3 text-sm text-slate-600">
        {data.total} results · page {data.page} of {data.total_pages}
        {loading ? " · updating…" : ""}
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
      <nav className="mt-4 flex items-center gap-3" aria-label="Pagination">
        <button
          type="button"
          disabled={!canPrev || loading}
          onClick={() => onPageChange(data.page - 1)}
          className="rounded-md border px-3 py-1 text-sm disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={!canNext || loading}
          onClick={() => onPageChange(data.page + 1)}
          className="rounded-md border px-3 py-1 text-sm disabled:opacity-40"
        >
          Next
        </button>
      </nav>
    </section>
  );
}