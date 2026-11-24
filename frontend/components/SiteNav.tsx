"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export function SiteNav() {
  const [unread, setUnread] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/alerts/notifications/unread-count")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setUnread(d?.unread_count ?? null))
      .catch(() => setUnread(null));
  }, []);

  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-semibold text-slate-900">
          Global Jobs
        </Link>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-700">
          <Link href="/" className="hover:text-slate-900">
            Search
          </Link>
          <Link href="/saved-searches" className="hover:text-slate-900">
            Saved searches
          </Link>
          <Link href="/notifications" className="hover:text-slate-900">
            Notifications
            {unread !== null && unread > 0 ? (
              <span className="ml-1 rounded-full bg-emerald-600 px-2 py-0.5 text-xs text-white">
                {unread}
              </span>
            ) : null}
          </Link>
          <Link href="/preferences" className="hover:text-slate-900">
            Digest settings
          </Link>
        </div>
      </nav>
    </header>
  );
}