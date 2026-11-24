"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ensureAlertSession } from "@/lib/client/alerts-session";
import { bffJson } from "@/lib/client/bff";

type Notif = {
  id: string;
  title: string | null;
  company: string | null;
  job_id: string;
  job_url: string | null;
  read_at: string | null;
};

type ListOut = { items: Notif[] };

export function NotificationsPage() {
  const [items, setItems] = useState<Notif[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      let res = await bffJson<ListOut>("/api/alerts/notifications?page_size=50");
      if (res.status === 401) {
        await ensureAlertSession();
        res = await bffJson<ListOut>("/api/alerts/notifications?page_size=50");
      }
      if (res.error) throw new Error(res.error);
      setItems(res.data?.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load notifications");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-4">
      {loading ? <p className="text-sm text-slate-600">Loading notifications…</p> : null}
      {error ? <p className="text-red-600">{error}</p> : null}
      <button
        type="button"
        className="rounded-md border px-3 py-1 text-sm"
        onClick={async () => {
          const res = await bffJson("/api/alerts/notifications/mark-read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mark_all: true }),
          });
          if (res.error) setError(res.error);
          else await load();
        }}
      >
        Mark all read
      </button>
      <ul className="space-y-2">
        {items.map((n) => (
          <li
            key={n.id}
            className={`rounded-lg border bg-white p-3 ${n.read_at ? "opacity-70" : ""}`}
          >
            <p className="font-medium">{n.title}</p>
            <p className="text-sm text-slate-600">{n.company}</p>
            <div className="mt-2 flex flex-wrap gap-3 text-sm">
              <Link href={`/jobs/${n.job_id}`} className="text-emerald-700 hover:underline">
                Job detail
              </Link>
              {n.job_url ? (
                <a
                  href={n.job_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-slate-600 hover:underline"
                >
                  Original URL
                </a>
              ) : null}
              {!n.read_at ? (
                <button
                  type="button"
                  className="text-slate-700"
                  onClick={async () => {
                    const res = await bffJson("/api/alerts/notifications/mark-read", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ notification_ids: [n.id] }),
                    });
                    if (res.error) setError(res.error);
                    else await load();
                  }}
                >
                  Mark read
                </button>
              ) : null}
              <button
                type="button"
                className="text-red-600"
                onClick={async () => {
                  const res = await bffJson(`/api/alerts/notifications/${n.id}`, {
                    method: "DELETE",
                  });
                  if (res.error) setError(res.error);
                  else await load();
                }}
              >
                Dismiss
              </button>
            </div>
          </li>
        ))}
      </ul>
      {!loading && items.length === 0 && !error ? (
        <p className="text-slate-600">No notifications.</p>
      ) : null}
    </div>
  );
}