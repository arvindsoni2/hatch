"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bot, FileText, LockKeyhole, SlidersHorizontal, Stethoscope, UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";

const SETTINGS_ITEMS = [
  { label: "Profile", href: "/settings/profile", icon: UserRound },
  { label: "Job Preferences", href: "/settings/preferences", icon: SlidersHorizontal },
  { label: "AI & Capabilities", href: "/settings/ai", icon: Bot },
  { label: "Master CV", href: "/settings/resume", icon: FileText },
  { label: "Security", href: "/settings/security", icon: LockKeyhole },
  { label: "Diagnostics", href: "/settings/system", icon: Stethoscope },
];

interface SettingsShellProps {
  activeHref: string;
  title: string;
  description: string;
  children: React.ReactNode;
}

export function SettingsShell({
  activeHref,
  title,
  description,
  children,
}: SettingsShellProps) {
  const router = useRouter();

  return (
    <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-6 lg:self-start">
        <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-3">
          <label className="mb-2 block text-xs font-semibold text-[var(--text-muted)] lg:hidden" htmlFor="settings-section">
            Settings section
          </label>
          <select
            aria-label="Settings section"
            className="mb-2 min-h-11 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)] lg:hidden"
            id="settings-section"
            onChange={(event) => router.push(event.target.value)}
            value={activeHref}
          >
            {SETTINGS_ITEMS.map((item) => (
              <option key={item.href} value={item.href}>{item.label}</option>
            ))}
          </select>
          <nav aria-label="Settings" className="hidden gap-1 lg:grid">
            {SETTINGS_ITEMS.map(({ label, href, icon: Icon }) => {
              const active = href === activeHref;
              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-h-11 items-center gap-3 rounded-[var(--radius-control)] px-3 text-sm font-medium transition-colors",
                    active
                      ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "text-[var(--text-dim)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]",
                  )}
                  href={href}
                  key={href}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>
      <div className="min-w-0 space-y-6">
        <header>
          <h1 className="text-[28px] font-semibold tracking-[-0.025em] text-[var(--text)]">
            {title}
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--text-muted)]">
            {description}
          </p>
        </header>
        {children}
      </div>
    </div>
  );
}

export { SETTINGS_ITEMS };
