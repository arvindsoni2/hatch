"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export const AI_SETUP_REMINDER_SNOOZE_KEY = "hatch_ai_setup_reminder";

interface AiSetupReminderProps {
  incomplete: boolean;
  actionRequired?: string | null;
  forceShow?: boolean;
}

function readSnooze() {
  try {
    const stored = JSON.parse(localStorage.getItem(AI_SETUP_REMINDER_SNOOZE_KEY) ?? "{}");
    return typeof stored.snoozed_until === "string" ? Date.parse(stored.snoozed_until) : 0;
  } catch {
    return 0;
  }
}

export function AiSetupReminder({ incomplete, actionRequired, forceShow = false }: AiSetupReminderProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!incomplete) {
      setVisible(false);
      return;
    }
    if (forceShow || readSnooze() <= Date.now()) {
      setVisible(true);
    }
  }, [forceShow, incomplete, actionRequired]);

  if (!visible) return null;

  const snooze = () => {
    const snoozedUntil = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
    localStorage.setItem(AI_SETUP_REMINDER_SNOOZE_KEY, JSON.stringify({ snoozed_until: snoozedUntil }));
    setVisible(false);
  };

  return (
    <section className="mb-4 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[var(--radius-control)] bg-[var(--accent-soft)] text-[var(--accent)]">
            <Bot className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">Finish setting up Hatch AI</h2>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--text-muted)]">
              CV tailoring, job scoring, and interview preparation are limited until an AI provider is configured.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            className="inline-flex min-h-10 items-center rounded-[var(--radius-control)] bg-[var(--accent)] px-3 text-sm font-semibold text-[var(--on-accent)]"
            href="/settings/ai"
          >
            Configure AI
          </Link>
          <Button aria-label="Not now" onClick={snooze} type="button" variant="ghost">
            <X className="h-4 w-4" aria-hidden="true" />
            Not now
          </Button>
        </div>
      </div>
    </section>
  );
}
