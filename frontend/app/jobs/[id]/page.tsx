import Link from "next/link";

import { getPublicJobsApiBase } from "@/lib/config";

type Props = { params: Promise<{ id: string }> };

export default async function JobDetailPage({ params }: Props) {
  const { id } = await params;
  const res = await fetch(`${getPublicJobsApiBase()}/api/v1/jobs/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return (
      <div>
        <p className="text-red-600">Job not found or no longer public.</p>
        <Link href="/" className="text-emerald-700 hover:underline">
          Back to search
        </Link>
      </div>
    );
  }
  const json = await res.json();
  const job = json.data;
  return (
    <article className="max-w-2xl space-y-4 rounded-xl border border-slate-200 bg-white p-6">
      <Link href="/" className="text-sm text-emerald-700 hover:underline">
        ← Back
      </Link>
      <h1 className="text-2xl font-semibold">{job.title}</h1>
      <p className="text-lg text-slate-700">{job.company}</p>
      <p className="text-sm text-slate-500">
        {[job.city, job.country_code, job.location_text].filter(Boolean).join(" · ")}
      </p>
      {job.job_url ? (
        <a
          href={job.job_url}
          className="inline-block rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800"
          target="_blank"
          rel="noopener noreferrer"
        >
          View original posting
        </a>
      ) : null}
    </article>
  );
}