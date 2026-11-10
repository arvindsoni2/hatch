"use client";

import Link from "next/link";

import { PatternCard } from "@/components/coach/readiness/PatternCard";
import { buttonVariants } from "@/components/ui/button";
import type { PatternGroupSection } from "@/lib/coachReadinessApi";
import { cn } from "@/lib/utils";

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

export function PatternGroup({
  group,
  onDismiss,
  onUndo,
}: {
  group: PatternGroupSection;
  onDismiss?: (fingerprint: string) => void;
  onUndo?: (fingerprint: string) => void;
}) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--text)]">
          {group.role_family} · {titleCase(group.interview_type)}
        </h3>
        <span className="text-xs text-[var(--text-dim)]">
          {group.session_count} assessed {group.session_count === 1 ? "session" : "sessions"}
        </span>
      </div>
      {group.patterns.length > 0 ? (
        <div className="space-y-3">
          {group.patterns.map((pattern) => (
            <PatternCard
              key={pattern.fingerprint}
              pattern={pattern}
              onDismiss={onDismiss}
              onUndo={onUndo}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-card)] border border-dashed border-[var(--border)] px-4 py-3">
          <p className="text-sm text-[var(--text-dim)]">
            Patterns appear after your second session here.
          </p>
          <Link href="/coach" className={cn(buttonVariants({ variant: "outline", size: "sm" }))}>
            Practise this role
          </Link>
        </div>
      )}
    </section>
  );
}
