export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-live="polite" aria-label="Loading Interview Coach">
      <span className="sr-only">Loading Interview Coach...</span>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="h-6 w-44 animate-pulse rounded bg-[var(--surface-3)]" />
        <div className="mt-3 h-4 w-80 max-w-full animate-pulse rounded bg-[var(--surface-2)]" />
      </div>
      {[0, 1, 2].map((index) => (
        <div
          key={index}
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4"
          data-testid="coach-loading-skeleton"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0 flex-1 space-y-2">
              <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--surface-3)]" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-[var(--surface-2)]" />
            </div>
            <div className="h-6 w-24 animate-pulse rounded-full bg-[var(--surface-2)]" />
          </div>
        </div>
      ))}
    </div>
  );
}
