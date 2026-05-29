"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Inbox,
  CheckCircle,
  LayoutDashboard,
  BarChart3,
  BookOpen,
  FileEdit,
  Settings,
  Sun,
  Moon,
  Bell,
} from "lucide-react";
import { fetchPendingApprovals, fetchRawProfile } from "@/lib/api";

const NAV_GROUPS = [
  {
    label: "Discover",
    items: [
      { href: "/", label: "Home", icon: Home, exact: true },
      { href: "/jobs", label: "Approval queue", icon: Inbox, badge: "approvals", badgeAccent: true },
      { href: "/approvals", label: "Approved", icon: CheckCircle },
    ],
  },
  {
    label: "Track",
    items: [
      { href: "/applications", label: "Pipeline", icon: LayoutDashboard },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Prepare",
    items: [
      { href: "/tailor", label: "Resume tailoring", icon: FileEdit },
      { href: "/coach", label: "Interview prep", icon: BookOpen },
    ],
  },
];

function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = localStorage.getItem("theme") as "dark" | "light" | null;
    const resolved = stored ?? "dark";
    setTheme(resolved);
    document.documentElement.setAttribute("data-theme", resolved);
    if (resolved === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, []);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
    document.documentElement.setAttribute("data-theme", next);
    if (next === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  return { theme, toggle };
}

export function Sidebar() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const [approvalCount, setApprovalCount] = useState(0);
  const [profileName, setProfileName] = useState<string | null>(null);
  const [profileTitle, setProfileTitle] = useState<string | null>(null);

  useEffect(() => {
    async function loadCount() {
      try {
        const approvals = await fetchPendingApprovals();
        setApprovalCount(approvals.length);
      } catch {
        // Non-critical
      }
    }
    void loadCount();
    const interval = setInterval(() => void loadCount(), 30_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    fetchRawProfile()
      .then((profile) => {
        if (profile.candidate?.name) setProfileName(profile.candidate.name);
        if (profile.candidate?.title) setProfileTitle(profile.candidate.title);
      })
      .catch(() => {});
  }, []);

  return (
    <aside
      className="hidden md:flex flex-col gap-1 sticky top-0 h-screen overflow-y-auto border-r"
      style={{
        width: "var(--sidebar-width)",
        background: "var(--bg)",
        borderColor: "var(--border)",
        padding: "20px 14px",
      }}
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-2 pb-4">
        <div
          className="flex items-center justify-center rounded-lg font-bold text-sm"
          style={{
            width: 28,
            height: 28,
            background: "var(--text)",
            color: "var(--bg)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          H
        </div>
        <span
          className="font-semibold"
          style={{ fontSize: 15, letterSpacing: "-0.015em", color: "var(--text)" }}
        >
          Hatch
        </span>
        <span
          className="ml-auto font-mono text-xs px-1.5 py-0.5 rounded"
          style={{
            color: "var(--text-muted)",
            border: "1px solid var(--border)",
            fontSize: 11,
          }}
        >
          beta
        </span>
      </div>

      {/* Nav groups */}
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <div
            className="font-medium uppercase px-2.5 py-1"
            style={{
              fontSize: 11,
              letterSpacing: "0.06em",
              color: "var(--text-muted)",
              paddingTop: 16,
              paddingBottom: 6,
            }}
          >
            {group.label}
          </div>
          {group.items.map((item) => {
            const Icon = item.icon;
            const isActive = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href) && item.href !== "/";
            const badgeCount = item.badge === "approvals" ? approvalCount : 0;

            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-2.5 w-full rounded-lg font-medium transition-colors"
                style={{
                  padding: "8px 10px",
                  fontSize: "13.5px",
                  color: isActive ? "var(--text)" : "var(--text-dim)",
                  background: isActive ? "var(--surface-2)" : "transparent",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <Icon
                  size={16}
                  style={{ flexShrink: 0, opacity: isActive ? 1 : 0.85 }}
                />
                <span>{item.label}</span>
                {badgeCount > 0 && (
                  <span
                    className="ml-auto font-mono font-medium"
                    style={{
                      fontSize: 11,
                      padding: "1px 7px",
                      borderRadius: 999,
                      background: item.badgeAccent ? "var(--accent-soft)" : "var(--surface-2)",
                      color: item.badgeAccent ? "var(--accent)" : "var(--text-dim)",
                    }}
                  >
                    {badgeCount > 99 ? "99+" : badgeCount}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}

      {/* Footer */}
      <div
        className="mt-auto pt-4 flex items-center gap-2"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link
          href="/settings"
          className="flex items-center gap-2.5 flex-1 rounded-lg p-2 transition-colors"
          style={{ color: "var(--text-dim)", borderRadius: "var(--radius-sm)" }}
        >
          <div
            className="flex items-center justify-center rounded-full font-semibold text-xs shrink-0"
            style={{
              width: 28,
              height: 28,
              background: "linear-gradient(135deg, #f97316, #ec4899)",
              color: "#fff",
            }}
          >
            {profileName
              ? profileName.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()
              : "?"}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium truncate" style={{ color: "var(--text)" }}>
              {profileName ?? "Profile"}
            </div>
            <div className="truncate" style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {profileTitle ?? "Settings"}
            </div>
          </div>
          <Settings size={14} />
        </Link>

        <button
          onClick={toggle}
          className="flex items-center justify-center rounded-lg transition-colors"
          style={{
            width: 32,
            height: 32,
            color: "var(--text-dim)",
            borderRadius: "var(--radius-sm)",
          }}
          title="Toggle theme"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <button
          className="flex items-center justify-center rounded-lg transition-colors"
          style={{
            width: 32,
            height: 32,
            color: "var(--text-dim)",
            borderRadius: "var(--radius-sm)",
          }}
          title="Notifications"
          aria-label="Notifications"
        >
          <Bell size={16} />
        </button>
      </div>
    </aside>
  );
}
