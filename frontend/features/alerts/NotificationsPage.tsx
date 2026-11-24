"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Notif = {
  id: string;
  title: string | null;
  company: string | null;
  job_id: string;
  job_url: string | null;
  read_at: string | null;
};

export function NotificationsPage() {
  const [items, setItems] = useState<Notif[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const res = await fetch("/api/alerts/notifications?page_size=50");
    if (!res.ok) {
      setError("Sign in via saved searches first (automatic registration).");
      return;
    }
    const data = await res.json();
    setItems(data.items ?? []);
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      {error ? <p className="text-red-600">{error}</p> : null}
      <button
        type="button"
        className="rounded-md border px-3 py-1 text-sm"
        onClick={async () => {
          await fetch("/api/alerts/notifications/mark-read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mark_all: true }),
          });
          await load();
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
                <a href={n.job_url} target="_blank" rel="noopener noreferrer" className="text-slate-600 hover:underline">
                  Original URL
                </a>
              ) : null}
              {!n.read_at ? (
                <button
                  type="button"
                  className="text-slate-700"
                  onClick={async () => {
                    await fetch("/api/alerts/notifications/mark-read", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ notification_ids: [n.id] }),
                    });
                    await load();
                  }}
                >
                  Mark read
                </button>
              ) : null}
              <button
                type="button"
                className="text-red-600"
                onClick={async () => {
                  await fetch(`/api/alerts/notifications/${n.id}`, { method: "DELETE" });
                  await load();
                }}
              >
                Dismiss
              </button>
            </div>
          </li>
        ))}
      </ul>
      {items.length === 0 && !error ? <p className="text-slate-600">No notifications.</p> : null}
    </div>
  );
}