"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Search, CheckSquare, Columns3, BarChart3, GraduationCap } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchPendingApprovals } from "@/lib/api";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

const BOTTOM_NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home, exact: true },
  { href: PRODUCT_ROUTES.jobs.href, label: PRODUCT_ROUTES.jobs.label, icon: Search, exact: false },
  { href: "/approvals", label: "Approvals", icon: CheckSquare, exact: false, badge: true },
  { href: PRODUCT_ROUTES.applications.href, label: PRODUCT_ROUTES.applications.label, icon: Columns3, exact: false },
  { href: "/analytics", label: "Analytics", icon: BarChart3, exact: false },
  { href: PRODUCT_ROUTES.interviewCoach.href, label: PRODUCT_ROUTES.interviewCoach.label, icon: GraduationCap, exact: false },
];

export function BottomNav() {
  const pathname = usePathname();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    async function loadCount() {
      try {
        const approvals = await fetchPendingApprovals();
        setPendingCount(approvals.length);
      } catch {
        // non-critical
      }
    }
    void loadCount();
    const interval = setInterval(() => void loadCount(), 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-slate-200 dark:border-slate-700 bg-white/95 dark:bg-slate-900/95 backdrop-blur-sm pb-safe md:hidden">
      <div className="flex items-stretch">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href) && item.href !== "/";

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] transition-colors min-h-[44px] justify-center ${
                isActive ? "text-blue-500 font-medium" : "text-slate-400 dark:text-slate-500"
              }`}
            >
              <span className="relative">
                <Icon size={20} />
                {item.badge && pendingCount > 0 && (
                  <span className="absolute -top-1.5 -right-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-medium text-white">
                    {pendingCount}
                  </span>
                )}
              </span>
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
