export default function Loading() {
  return (
    <div className="space-y-3" role="status" aria-live="polite" aria-label="Loading Pipeline">
      <span className="sr-only">Loading Pipeline...</span>
      {[0, 1, 2].map((index) => (
        <div
          key={index}
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4"
          data-testid="pipeline-loading-skeleton"
        >
          <div className="grid gap-3 md:grid-cols-[minmax(180px,1.35fr)_72px_minmax(160px,210px)_148px_110px]">
            <div className="space-y-2">
              <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--surface-3)]" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-[var(--surface-2)]" />
            </div>
            <div className="h-8 w-14 animate-pulse rounded-full bg-[var(--surface-3)]" />
            <div className="h-8 animate-pulse rounded bg-[var(--surface-2)]" />
            <div className="h-4 animate-pulse rounded bg-[var(--surface-2)]" />
            <div className="h-9 animate-pulse rounded bg-[var(--surface-3)]" />
          </div>
        </div>
      ))}
    </div>
  );
}
