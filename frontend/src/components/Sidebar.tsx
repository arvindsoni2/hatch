"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
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
import { fetchPendingApprovals, fetchRawProfile, fetchAllAgentStatus, type AllAgentStatus } from "@/lib/api";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

const NAV_GROUPS = [
  {
    label: "Discover",
    items: [
      { href: "/", label: "Home", icon: Home, exact: true },
      { href: PRODUCT_ROUTES.jobs.href, label: PRODUCT_ROUTES.jobs.label, icon: Inbox, badge: "approvals", badgeAccent: true },
      { href: "/approvals", label: "Shortlist", icon: CheckCircle },
    ],
  },
  {
    label: "Track",
    items: [
      { href: PRODUCT_ROUTES.applications.href, label: PRODUCT_ROUTES.applications.label, icon: LayoutDashboard },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Prepare",
    items: [
      { href: "/tailor", label: "CV Studio", icon: FileEdit },
      { href: PRODUCT_ROUTES.interviewCoach.href, label: PRODUCT_ROUTES.interviewCoach.label, icon: BookOpen },
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
  const [agentStatus, setAgentStatus] = useState<AllAgentStatus | null>(null);
  const [notifOpen, setNotifOpen] = useState(false);
  const [popPos, setPopPos] = useState<{ left: number; bottom: number } | null>(null);
  const bellRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [approvals, status] = await Promise.all([
          fetchPendingApprovals(),
          fetchAllAgentStatus().catch(() => null),
        ]);
        setApprovalCount(approvals.length);
        setAgentStatus(status);
      } catch {
        // Non-critical
      }
    }
    void loadData();
    const interval = setInterval(() => void loadData(), 30_000);
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

  const computePos = useCallback(() => {
    if (!bellRef.current) return;
    const r = bellRef.current.getBoundingClientRect();
    const W = 312, M = 8;
    let left = r.right + 8;
    left = Math.min(left, window.innerWidth - W - M);
    left = Math.max(M, left);
    let bottom = window.innerHeight - r.top + 8;
    bottom = Math.min(bottom, window.innerHeight - M);
    setPopPos({ left, bottom });
  }, []);

  useEffect(() => {
    if (!notifOpen) return;
    computePos();
    window.addEventListener("resize", computePos);
    window.addEventListener("scroll", computePos, true);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setNotifOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", computePos);
      window.removeEventListener("scroll", computePos, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [notifOpen, computePos]);

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
          href="/settings/profile"
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
              {profileTitle ?? "Profile"}
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

        <div className="relative">
          <button
            ref={bellRef}
            onClick={() => setNotifOpen((o) => !o)}
            className="flex items-center justify-center rounded-lg transition-colors relative"
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
            {(() => {
              const errorAgents = agentStatus?.agents.filter((a) => a.status === "error").length ?? 0;
              const total = approvalCount + errorAgents;
              return total > 0 ? (
                <span
                  className="absolute -top-1 -right-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full text-[10px] font-bold leading-none text-white"
                  style={{ background: "var(--danger)", padding: "0 3px" }}
                >
                  {total > 9 ? "9+" : total}
                </span>
              ) : null;
            })()}
          </button>

          {notifOpen && popPos && typeof document !== "undefined" && createPortal(
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-[59]"
                onClick={() => setNotifOpen(false)}
              />
              {/* Panel — portalled to body, fixed-positioned, clamped to viewport */}
              <div
                className="fixed z-[60] w-[312px] rounded-xl shadow-xl overflow-hidden"
                style={{
                  left: popPos.left,
                  bottom: popPos.bottom,
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  animation: "notifRise .14s ease-out",
                }}
              >
                <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
                  <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>Notifications</span>
                  <button
                    onClick={() => setNotifOpen(false)}
                    className="text-xs"
                    style={{ color: "var(--text-muted)" }}
                  >
                    ✕
                  </button>
                </div>

                <div className="max-h-72 overflow-y-auto">
                  {approvalCount > 0 && (
                    <Link
                      href="/approvals"
                      onClick={() => setNotifOpen(false)}
                      className="flex items-start gap-3 px-4 py-3 hover:bg-slate-100 transition-colors border-b"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <span
                        className="mt-0.5 h-2 w-2 rounded-full shrink-0"
                        style={{ background: "var(--accent)" }}
                      />
                      <div>
                        <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                          {approvalCount} application{approvalCount !== 1 ? "s" : ""} awaiting approval
                        </p>
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Review in Approved queue</p>
                      </div>
                    </Link>
                  )}

                  {agentStatus?.agents.filter((a) => a.status === "error").map((a) => (
                    <Link
                      key={a.agent_name}
                      href="/analytics"
                      onClick={() => setNotifOpen(false)}
                      className="flex items-start gap-3 px-4 py-3 hover:bg-slate-100 transition-colors border-b"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <span
                        className="mt-0.5 h-2 w-2 rounded-full shrink-0"
                        style={{ background: "var(--danger)" }}
                      />
                      <div>
                        <p className="text-sm font-medium capitalize" style={{ color: "var(--text)" }}>
                          {a.agent_name} agent error
                        </p>
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>View in Analytics</p>
                      </div>
                    </Link>
                  ))}

                  {approvalCount === 0 && (agentStatus?.agents.filter((a) => a.status === "error").length ?? 0) === 0 && (
                    <div className="px-4 py-6 text-center">
                      <p className="text-sm" style={{ color: "var(--text-muted)" }}>All clear — no pending notifications</p>
                    </div>
                  )}
                </div>

                <div className="px-4 py-2 border-t" style={{ borderColor: "var(--border)" }}>
                  <Link
                    href="/analytics"
                    onClick={() => setNotifOpen(false)}
                    className="text-xs"
                    style={{ color: "var(--accent)" }}
                  >
                    View agent log →
                  </Link>
                </div>
              </div>
            </>,
            document.body
          )}
        </div>
      </div>
    </aside>
  );
}
