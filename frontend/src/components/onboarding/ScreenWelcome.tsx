"use client";

import { Search, Scale, FileText, Kanban, MessageSquare, ShieldCheck, Check } from "lucide-react";

const VALUE_STEPS = [
  { Icon: Search,        title: "Discover", sub: "Scans your job boards every few hours" },
  { Icon: Scale,         title: "Score",    sub: "Ranks each role against your profile" },
  { Icon: FileText,      title: "Tailor",   sub: "Drafts a tuned CV + cover letter" },
  { Icon: Kanban,        title: "Track",    sub: "You approve. It never applies on its own" },
  { Icon: MessageSquare, title: "Coach",    sub: "Preps you when an interview lands" },
];

interface ScreenWelcomeProps {
  hasSaved: boolean;
  onStart: () => void;
}

export function ScreenWelcome({ hasSaved, onStart }: ScreenWelcomeProps) {
  return (
    <div className="ob-fadein flex flex-col min-h-full px-5 pt-6 pb-2">
      {/* Hero mark */}
      <div
        className="w-14 h-14 rounded-[16px] grid place-items-center font-[800] text-[28px] text-white mb-5 shadow-[0_10px_30px_-8px_var(--accent-soft-strong)]"
        style={{ background: "linear-gradient(135deg, var(--accent), var(--success))" }}
      >
        H
      </div>

      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2.5">
        Welcome to Hatch
      </p>

      <h1 className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
        Your job search,<br />on autopilot.
      </h1>

      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-5">
        Hatch finds, scores and tailors applications for roles that fit you, then hands you the
        decisions that matter. You stay in control; it never applies on its own. Setup takes about
        3 minutes.
      </p>

      {/* Pipeline */}
      <div className="flex flex-col gap-0.5 mb-5">
        {VALUE_STEPS.map(({ Icon, title, sub }, i) => (
          <div key={title}>
            <div className="flex gap-3 py-2">
              <div
                className="w-[30px] h-[30px] rounded-[9px] flex-shrink-0 grid place-items-center text-[var(--accent)]"
                style={{ background: "var(--surface-2)" }}
              >
                <Icon size={16} />
              </div>
              <span className="flex flex-col">
                <span className="text-[13.5px] font-[600] text-[var(--text)]">{title}</span>
                <span className="text-[12px] text-[var(--text-muted)] mt-0.5 leading-[1.4]">{sub}</span>
              </span>
            </div>
            {i < VALUE_STEPS.length - 1 && (
              <div className="w-px ml-[14px] h-1.5" style={{ background: "var(--border)" }} />
            )}
          </div>
        ))}
      </div>

      {/* Trust chips */}
      <div className="flex flex-wrap gap-2 mb-6">
        <span
          className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--text-dim)] px-2.5 py-1.5 rounded-full border border-[var(--border)]"
          style={{ background: "var(--surface)" }}
        >
          <ShieldCheck size={13} className="text-[var(--success)]" />
          Self-hosted. Data stays on your machine
        </span>
        <span
          className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--text-dim)] px-2.5 py-1.5 rounded-full border border-[var(--border)]"
          style={{ background: "var(--surface)" }}
        >
          <Check size={13} className="text-[var(--success)]" />
          Never auto-applies
        </span>
      </div>

      {/* CTA */}
      <button
        type="button"
        onClick={onStart}
        className="w-full py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] flex items-center justify-center gap-2 transition-colors hover:opacity-90"
        style={{ background: "var(--accent)" }}
      >
        {hasSaved ? "Resume setup" : "Get started"} →
      </button>
    </div>
  );
}
