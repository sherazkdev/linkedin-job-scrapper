"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  ensureAlertSession,
  fetchAlertSession,
  logoutAlertSession,
} from "@/lib/client/alerts-session";
import { bffJson } from "@/lib/client/bff";

type Search = {
  id: string;
  q: string | null;
  country_code: string | null;
  digest_enabled: boolean;
  digest_timezone: string;
  digest_local_time: string | null;
  digest_max_jobs: number;
  alerts_enabled: boolean;
};

export function PreferencesPage() {
  const [preview, setPreview] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [targetSearch, setTargetSearch] = useState<Search | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        await ensureAlertSession();
        const list = await bffJson<Search[]>("/api/alerts/searches");
        if (list.error) throw new Error(list.error);
        const rows = list.data ?? [];
        const digestRow =
          rows.find((s) => s.digest_enabled) ??
          rows.find((s) => s.q && s.country_code) ??
          rows[0] ??
          null;
        setTargetSearch(digestRow);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load preferences");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onSaveDigest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSaved(null);
    const fd = new FormData(e.currentTarget);
    const digestPatch = {
      digest_enabled: true,
      digest_timezone: String(fd.get("digest_timezone")),
      digest_local_time: String(fd.get("digest_local_time")),
      digest_max_jobs: Number(fd.get("digest_max_jobs") || 10),
    };
    try {
      await ensureAlertSession();
      const before = await fetchAlertSession();
      const sessionId = before.subscriber_id;

      if (targetSearch) {
        const res = await bffJson(`/api/alerts/searches/${targetSearch.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(digestPatch),
        });
        if (res.error) throw new Error(res.error);
      } else {
        const res = await bffJson("/api/alerts/searches", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            q: String(fd.get("q") || "engineer"),
            country_code: String(fd.get("country_code") || "PK"),
            alerts_enabled: true,
            ...digestPatch,
          }),
        });
        if (res.error) throw new Error(res.error);
      }

      const after = await fetchAlertSession();
      if (sessionId && after.subscriber_id && sessionId !== after.subscriber_id) {
        throw new Error("Session identity changed unexpectedly");
      }
      setSaved("Digest preferences saved on your existing subscriber.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function runPreview() {
    setError(null);
    try {
      await ensureAlertSession();
      const res = await bffJson("/api/alerts/digest/preview", { method: "POST" });
      if (res.error) throw new Error(res.error);
      setPreview(res.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
        <strong>In-app alerts</strong> can be enabled per saved search. <strong>Daily digest</strong>{" "}
        delivery is not automatically scheduled (no Celery Beat). Preview below is read-only.
      </p>
      {loading ? <p className="text-sm text-slate-600">Loading…</p> : null}
      <form onSubmit={onSaveDigest} className="space-y-3 rounded-xl border bg-white p-4">
        <h2 className="font-medium">Daily digest preferences</h2>
        {!targetSearch ? (
          <>
            <label className="block text-sm">
              Search keyword
              <input name="q" defaultValue="engineer" className="mt-1 w-full rounded border px-3 py-2" />
            </label>
            <label className="block text-sm">
              Country
              <input name="country_code" defaultValue="PK" maxLength={2} className="mt-1 w-full rounded border px-3 py-2 uppercase" />
            </label>
          </>
        ) : (
          <p className="text-sm text-slate-600">
            Updating digest on: {[targetSearch.q, targetSearch.country_code].filter(Boolean).join(" · ")}
          </p>
        )}
        <input
          name="digest_timezone"
          defaultValue={targetSearch?.digest_timezone ?? "Asia/Karachi"}
          className="w-full rounded border px-3 py-2"
          placeholder="Timezone"
          required
        />
        <input
          name="digest_local_time"
          defaultValue={targetSearch?.digest_local_time ?? "09:00"}
          pattern="\d{2}:\d{2}"
          className="w-full rounded border px-3 py-2"
          required
        />
        <input
          name="digest_max_jobs"
          type="number"
          min={1}
          max={50}
          defaultValue={targetSearch?.digest_max_jobs ?? 10}
          className="w-full rounded border px-3 py-2"
        />
        <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-white">
          Save digest settings
        </button>
      </form>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={runPreview} className="rounded-md border px-4 py-2 text-sm">
          Run digest preview
        </button>
        <button
          type="button"
          className="rounded-md border border-red-200 px-4 py-2 text-sm text-red-700"
          onClick={async () => {
            await logoutAlertSession();
            setTargetSearch(null);
            setError(null);
            setSaved("Signed out (session cookie cleared).");
          }}
        >
          Sign out alerts
        </button>
      </div>
      {saved ? <p className="text-sm text-emerald-700">{saved}</p> : null}
      {error ? <p className="text-red-600">{error}</p> : null}
      {preview ? (
        <pre className="overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
          {JSON.stringify(preview, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}