"use client";

import { FormEvent, useState } from "react";

export function PreferencesPage() {
  const [preview, setPreview] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSaveDigest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const fd = new FormData(e.currentTarget);
    const body = {
      q: String(fd.get("q") || "engineer"),
      country_code: String(fd.get("country_code") || "PK"),
      alerts_enabled: true,
      digest_enabled: true,
      digest_timezone: String(fd.get("digest_timezone")),
      digest_local_time: String(fd.get("digest_local_time")),
      digest_max_jobs: Number(fd.get("digest_max_jobs") || 10),
    };
    const reg = await fetch("/api/alerts/register", { method: "POST" });
    if (!reg.ok) {
      setError("Could not start alert session");
      return;
    }
    const res = await fetch("/api/alerts/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const b = await res.json();
      setError(b.detail ?? b.error ?? "Save failed");
    }
  }

  async function runPreview() {
    setError(null);
    const res = await fetch("/api/alerts/digest/preview", { method: "POST" });
    const data = await res.json();
    if (!res.ok) setError(data.error ?? "Preview failed");
    else setPreview(data);
  }

  return (
    <div className="space-y-6 max-w-xl">
      <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
        Daily digest delivery is not automatically scheduled yet. Preview is read-only and does not
        create notifications.
      </p>
      <form onSubmit={onSaveDigest} className="space-y-3 rounded-xl border bg-white p-4">
        <h2 className="font-medium">Subscriber digest schedule</h2>
        <input name="digest_timezone" defaultValue="Asia/Karachi" className="w-full rounded border px-3 py-2" placeholder="Timezone" />
        <input name="digest_local_time" defaultValue="09:00" pattern="\d{2}:\d{2}" className="w-full rounded border px-3 py-2" />
        <input name="digest_max_jobs" type="number" min={1} max={50} defaultValue={10} className="w-full rounded border px-3 py-2" />
        <input name="country_code" defaultValue="PK" className="w-full rounded border px-3 py-2" />
        <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-white">
          Save via new digest-enabled search
        </button>
      </form>
      <button type="button" onClick={runPreview} className="rounded-md border px-4 py-2 text-sm">
        Run digest preview
      </button>
      {error ? <p className="text-red-600">{error}</p> : null}
      {preview ? (
        <pre className="overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
          {JSON.stringify(preview, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}