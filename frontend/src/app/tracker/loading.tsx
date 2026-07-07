export default function Loading() {
  return (
    <div className="space-y-3" role="status" aria-live="polite" aria-label="Loading Applications">
      <span className="sr-only">Loading Applications...</span>
      <div className="flex gap-3 overflow-hidden pb-4">
        {[0, 1, 2, 3].map((index) => (
          <div
            key={index}
            className="min-h-[220px] w-[238px] shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-3"
            data-testid="applications-loading-skeleton"
          >
            <div className="mb-4 h-4 w-24 animate-pulse rounded bg-[var(--surface-3)]" />
            <div className="space-y-3">
              <div className="h-20 animate-pulse rounded-xl bg-[var(--surface-2)]" />
              <div className="h-16 animate-pulse rounded-xl bg-[var(--surface-2)]" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
