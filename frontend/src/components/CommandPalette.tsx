"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Home, Briefcase, Activity, Mic, Settings, BookOpen,
  Search, TrendingUp, BarChart2, Bell,
} from "lucide-react";

const COMMANDS = [
  { group: "Navigate", items: [
    { label: "Today",           icon: Home,       href: "/today" },
    { label: "Jobs",            icon: Briefcase,  href: "/jobs" },
    { label: "Tracker",         icon: Activity,   href: "/tracker" },
    { label: "Coach",           icon: Mic,        href: "/coach" },
    { label: "Prep",            icon: BookOpen,   href: "/prep" },
    { label: "Analytics",       icon: BarChart2,  href: "/analytics" },
    { label: "Activity Stream", icon: TrendingUp, href: "/stream" },
    { label: "Profile Settings", icon: Settings,  href: "/settings/profile" },
    { label: "AI Provider",      icon: Settings,  href: "/settings/ai" },
  ]},
  { group: "Actions", items: [
    { label: "Browse all jobs",  icon: Search,  href: "/jobs?showAll=true" },
    { label: "System Logs",     icon: Bell,    href: "/settings/system" },
  ]},
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  const handleOpen = useCallback(() => setOpen((v) => !v), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        handleOpen();
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, handleOpen]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" aria-hidden="true" />

      {/* Palette */}
      <div
        className="relative w-full max-w-[520px] mx-4 rounded-[var(--r-card,12px)] shadow-2xl overflow-hidden"
        style={{ background: "var(--surface)", border: "1px solid var(--border-strong)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <Command label="Command palette">
          <div
            className="flex items-center gap-3 px-4 py-3"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <Search className="h-4 w-4 shrink-0 text-[var(--text-dim)]" aria-hidden="true" />
            <Command.Input
              placeholder="Search pages and actions…"
              className="flex-1 bg-transparent text-[14px] text-[var(--text)] placeholder:text-[var(--text-dim)] outline-none"
              autoFocus
            />
            <kbd className="text-[11px] text-[var(--text-dim)] shrink-0">ESC</kbd>
          </div>

          <Command.List className="max-h-[360px] overflow-y-auto py-2">
            <Command.Empty className="py-8 text-center text-[13px] text-[var(--text-dim)]">
              No results found.
            </Command.Empty>

            {COMMANDS.map(({ group, items }) => (
              <Command.Group
                key={group}
                heading={group}
                className="[&>[cmdk-group-heading]]:px-4 [&>[cmdk-group-heading]]:py-1.5 [&>[cmdk-group-heading]]:text-[11px] [&>[cmdk-group-heading]]:font-[600] [&>[cmdk-group-heading]]:uppercase [&>[cmdk-group-heading]]:tracking-[0.08em] [&>[cmdk-group-heading]]:text-[var(--text-dim)]"
              >
                {items.map(({ label, icon: Icon, href }) => (
                  <Command.Item
                    key={href}
                    value={label}
                    onSelect={() => {
                      router.push(href);
                      setOpen(false);
                    }}
                    className="flex items-center gap-3 px-4 py-2.5 text-[13px] text-[var(--text)] cursor-pointer
                      aria-selected:bg-[var(--surface-2)] aria-selected:text-[var(--text)]
                      hover:bg-[var(--surface-2)] transition-colors"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-[var(--text-dim)]" aria-hidden="true" />
                    {label}
                  </Command.Item>
                ))}
              </Command.Group>
            ))}
          </Command.List>

          <div
            className="flex items-center justify-end gap-4 px-4 py-2 text-[11px] text-[var(--text-dim)]"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <span><kbd>↑↓</kbd> navigate</span>
            <span><kbd>↵</kbd> open</span>
            <span><kbd>⌘K</kbd> toggle</span>
          </div>
        </Command>
      </div>
    </div>
  );
}
