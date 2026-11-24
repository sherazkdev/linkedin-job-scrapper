"use client";

import { FormEvent, useEffect, useState } from "react";

import { ensureAlertSession } from "@/lib/client/alerts-session";
import { bffJson } from "@/lib/client/bff";

type Search = {
  id: string;
  q: string | null;
  country_code: string | null;
  city: string | null;
  alerts_enabled: boolean;
  digest_enabled?: boolean;
};

export function SavedSearchesPage() {
  const [searches, setSearches] = useState<Search[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionReady, setSessionReady] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      let list = await bffJson<Search[]>("/api/alerts/searches");
      if (list.status === 401) {
        await ensureAlertSession();
        list = await bffJson<Search[]>("/api/alerts/searches");
      }
      if (list.error) throw new Error(list.error);
      setSearches(list.data ?? []);
      setSessionReady(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    try {
      await ensureAlertSession();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session error");
      return;
    }
    const fd = new FormData(e.currentTarget);
    const body = {
      q: String(fd.get("q") || "") || null,
      country_code: String(fd.get("country_code") || "") || null,
      city: String(fd.get("city") || "") || null,
      alerts_enabled: true,
    };
    const res = await bffJson("/api/alerts/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.error) {
      setError(res.error);
      return;
    }
    (e.target as HTMLFormElement).reset();
    await load();
  }

  async function onEdit(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault();
    setError(null);
    const fd = new FormData(e.currentTarget);
    const body = {
      q: String(fd.get("q") || "") || null,
      country_code: String(fd.get("country_code") || "") || null,
      city: String(fd.get("city") || "") || null,
    };
    const res = await bffJson(`/api/alerts/searches/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.error) {
      setError(res.error);
      return;
    }
    setEditingId(null);
    await load();
  }

  return (
    <div className="space-y-6">
      {sessionReady ? (
        <p className="text-sm text-emerald-700">
          Alert session active (HttpOnly cookie). In-app alerts are separate from automatic digest
          email delivery.
        </p>
      ) : null}
      {loading ? <p className="text-sm text-slate-600">Loading saved searches…</p> : null}
      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      <form onSubmit={onCreate} className="grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-3">
        <input name="q" placeholder="Keyword" className="rounded-md border px-3 py-2" required />
        <input
          name="country_code"
          placeholder="Country (PK)"
          maxLength={2}
          className="rounded-md border px-3 py-2 uppercase"
        />
        <input name="city" placeholder="City" className="rounded-md border px-3 py-2" />
        <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-white sm:col-span-3">
          Save search
        </button>
      </form>
      <ul className="space-y-2">
        {searches.map((s) => (
          <li key={s.id} className="rounded-lg border bg-white p-3">
            {editingId === s.id ? (
              <form onSubmit={(e) => onEdit(e, s.id)} className="grid gap-2 sm:grid-cols-3">
                <input name="q" defaultValue={s.q ?? ""} className="rounded border px-2 py-1" />
                <input
                  name="country_code"
                  defaultValue={s.country_code ?? ""}
                  maxLength={2}
                  className="rounded border px-2 py-1 uppercase"
                />
                <input name="city" defaultValue={s.city ?? ""} className="rounded border px-2 py-1" />
                <div className="flex gap-2 sm:col-span-3">
                  <button type="submit" className="text-sm text-emerald-700">
                    Save
                  </button>
                  <button type="button" className="text-sm" onClick={() => setEditingId(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm">
                  {[s.q, s.country_code, s.city].filter(Boolean).join(" · ") || "Open search"}
                  <span className="ml-2 text-xs text-slate-500">
                    {s.alerts_enabled ? "Alerts on" : "Alerts off"}
                  </span>
                </span>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="text-sm" onClick={() => setEditingId(s.id)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    className="text-sm text-emerald-700"
                    onClick={async () => {
                      const path = s.alerts_enabled ? "disable" : "enable";
                      const res = await bffJson(`/api/alerts/searches/${s.id}/${path}`, {
                        method: "POST",
                      });
                      if (res.error) setError(res.error);
                      else await load();
                    }}
                  >
                    {s.alerts_enabled ? "Disable alerts" : "Enable alerts"}
                  </button>
                  <button
                    type="button"
                    className="text-sm text-red-600"
                    onClick={async () => {
                      const res = await bffJson(`/api/alerts/searches/${s.id}`, { method: "DELETE" });
                      if (res.error) setError(res.error);
                      else await load();
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
      {!loading && searches.length === 0 ? (
        <p className="text-slate-600">No saved searches yet.</p>
      ) : null}
    </div>
  );
}