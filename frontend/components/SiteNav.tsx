"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { bffJson } from "@/lib/client/bff";

export function SiteNav() {
  const [unread, setUnread] = useState<number | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    void (async () => {
      const res = await bffJson<{ unread_count: number }>("/api/alerts/notifications/unread-count");
      if (res.status === 401) {
        setUnread(null);
        return;
      }
      setUnread(res.data?.unread_count ?? 0);
    })();
  }, [pathname]);

  const linkClass = (path: string) =>
    pathname === path ? "font-medium text-slate-900" : "hover:text-slate-900";

  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-semibold text-slate-900">
          Global Jobs
        </Link>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-700">
          <Link href="/" className={linkClass("/")}>
            Search
          </Link>
          <Link href="/saved-searches" className={linkClass("/saved-searches")}>
            Saved searches
          </Link>
          <Link href="/notifications" className={linkClass("/notifications")}>
            Notifications
            {unread !== null && unread > 0 ? (
              <span className="ml-1 rounded-full bg-emerald-600 px-2 py-0.5 text-xs text-white">
                {unread}
              </span>
            ) : null}
          </Link>
          <Link href="/preferences" className={linkClass("/preferences")}>
            Digest settings
          </Link>
        </div>
      </nav>
    </header>
  );
}