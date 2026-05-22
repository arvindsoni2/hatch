"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings } from "lucide-react";
import { fetchPendingApprovals } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "Home", exact: true },
  { href: "/jobs", label: "Jobs", exact: false },
  { href: "/approvals", label: "Approvals", exact: false, badge: true },
  { href: "/applications", label: "Pipeline", exact: false },
  { href: "/coach", label: "Interview prep", exact: false },
];

export function Navigation() {
  const pathname = usePathname();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    async function loadCount() {
      try {
        const approvals = await fetchPendingApprovals();
        setPendingCount(approvals.length);
      } catch {
        // Non-critical — badge just shows nothing
      }
    }
    void loadCount();
    const interval = setInterval(() => void loadCount(), 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
            <span className="text-sm font-bold text-white">JP</span>
          </div>
          <span className="text-lg font-semibold text-slate-900">JobPilot</span>
        </Link>

        {/* Nav items */}
        <nav className="flex items-center gap-0.5 text-sm font-medium">
          {NAV_ITEMS.map((item) => {
            const isActive = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href) && item.href !== "/";
            const count = item.badge ? pendingCount : 0;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative flex items-center gap-1.5 rounded-md px-3 py-2 transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700 font-semibold"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                {item.label}
                {count > 0 && (
                  <span className="flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-red-500 px-1 text-xs font-semibold text-white leading-none">
                    {count > 99 ? "99+" : count}
                  </span>
                )}
              </Link>
            );
          })}

          {/* Settings gear */}
          <Link
            href="/settings"
            className={`ml-1 flex items-center justify-center rounded-md p-2 transition-colors ${
              pathname.startsWith("/settings")
                ? "bg-brand-50 text-brand-700"
                : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            }`}
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </Link>
        </nav>
      </div>
    </header>
  );
}
