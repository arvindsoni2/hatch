"use client";

import { Button } from "@/components/ui/button";

export function PatternTips({
  tips,
  loading,
  aiOff = false,
  unavailable = false,
  onRetry,
}: {
  tips: string[] | null;
  loading: boolean;
  aiOff?: boolean;
  unavailable?: boolean;
  onRetry?: () => void;
}) {
  return (
    <div className="mt-3 rounded-[var(--radius-control)] bg-[var(--surface)] p-3" aria-live="polite">
      <h4 className="text-xs font-semibold text-[var(--text)]">Tips</h4>
      {loading ? (
        <>
          <p className="mt-1 text-xs text-[var(--text-dim)]">Adding tips…</p>
          <div className="mt-2 space-y-2" aria-label="Adding tips">
            {[1, 2, 3].map((line) => (
              <div key={line} className="h-3 animate-pulse rounded bg-[var(--surface-3)]" />
            ))}
          </div>
        </>
      ) : null}
      {!loading && aiOff ? (
        <p className="mt-2 text-sm text-[var(--text-dim)]">Turn on local AI for tips</p>
      ) : null}
      {!loading && unavailable ? (
        <Button type="button" variant="ghost" size="sm" onClick={onRetry}>
          Tips unavailable — try again
        </Button>
      ) : null}
      {!loading && tips && tips.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-[var(--text-dim)]">
          {tips.map((tip) => <li key={tip}>{tip}</li>)}
        </ul>
      ) : null}
    </div>
  );
}
