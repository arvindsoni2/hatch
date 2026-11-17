"use client";

export function PatternTips({
  tips,
  loading,
  error,
}: {
  tips: string[] | null;
  loading: boolean;
  error?: string | null;
}) {
  return (
    <div className="mt-3 rounded-[var(--radius-control)] bg-[var(--surface)] p-3" aria-live="polite">
      <h4 className="text-xs font-semibold text-[var(--text)]">Tips</h4>
      {loading ? (
        <div className="mt-2 space-y-2" aria-label="Adding tips">
          {[1, 2, 3].map((line) => (
            <div key={line} className="h-3 animate-pulse rounded bg-[var(--surface-3)]" />
          ))}
        </div>
      ) : null}
      {!loading && tips && tips.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-[var(--text-dim)]">
          {tips.map((tip) => <li key={tip}>{tip}</li>)}
        </ul>
      ) : null}
      {!loading && error ? (
        <p className="mt-2 text-sm text-[var(--text-dim)]">Tips unavailable — try again</p>
      ) : null}
    </div>
  );
}
