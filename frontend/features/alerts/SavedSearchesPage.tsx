"use client";

import { FormEvent, useEffect, useState } from "react";

type Search = {
  id: string;
  q: string | null;
  country_code: string | null;
  city: string | null;
  alerts_enabled: boolean;
};

export function SavedSearchesPage() {
  const [searches, setSearches] = useState<Search[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  async function ensureSession() {
    const res = await fetch("/api/alerts/register", { method: "POST" });
    if (!res.ok) {
      const b = await res.json();
      throw new Error(b.error ?? "Registration failed");
    }
    setRegistered(true);
  }

  async function load() {
    try {
      const res = await fetch("/api/alerts/searches");
      if (res.status === 401) {
        await ensureSession();
        return load();
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to load");
      setSearches(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const fd = new FormData(e.currentTarget);
    const body = {
      q: String(fd.get("q") || "") || null,
      country_code: String(fd.get("country_code") || "") || null,
      city: String(fd.get("city") || "") || null,
      alerts_enabled: true,
    };
    const res = await fetch("/api/alerts/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const b = await res.json();
      setError(b.error ?? b.detail ?? "Could not create");
      return;
    }
    (e.target as HTMLFormElement).reset();
    await load();
  }

  return (
    <div className="space-y-6">
      {registered ? (
        <p className="text-sm text-emerald-700">Anonymous alert session active (HttpOnly cookie).</p>
      ) : null}
      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      <form onSubmit={onCreate} className="grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-3">
        <input name="q" placeholder="Keyword" className="rounded-md border px-3 py-2" />
        <input name="country_code" placeholder="Country" maxLength={2} className="rounded-md border px-3 py-2 uppercase" />
        <input name="city" placeholder="City" className="rounded-md border px-3 py-2" />
        <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-white sm:col-span-3">
          Save search
        </button>
      </form>
      <ul className="space-y-2">
        {searches.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-white p-3">
            <span className="text-sm">
              {[s.q, s.country_code, s.city].filter(Boolean).join(" · ") || "Open search"}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                className="text-sm text-emerald-700"
                onClick={async () => {
                  const path = s.alerts_enabled ? "disable" : "enable";
                  await fetch(`/api/alerts/searches/${s.id}/${path}`, { method: "POST" });
                  await load();
                }}
              >
                {s.alerts_enabled ? "Disable alerts" : "Enable alerts"}
              </button>
              <button
                type="button"
                className="text-sm text-red-600"
                onClick={async () => {
                  await fetch(`/api/alerts/searches/${s.id}`, { method: "DELETE" });
                  await load();
                }}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
      {searches.length === 0 ? <p className="text-slate-600">No saved searches yet.</p> : null}
    </div>
  );
}