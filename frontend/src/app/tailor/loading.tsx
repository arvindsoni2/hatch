export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-live="polite" aria-label="Loading CV Studio">
      <span className="sr-only">Loading CV Studio...</span>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
        <div className="h-5 w-40 animate-pulse rounded bg-[var(--surface-3)]" />
        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="h-16 animate-pulse rounded-lg bg-[var(--surface-2)]" />
          ))}
        </div>
      </div>
      {[0, 1, 2].map((index) => (
        <div
          key={index}
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
          data-testid="cv-studio-loading-skeleton"
        >
          <div className="space-y-3">
            <div className="h-4 w-1/3 animate-pulse rounded bg-[var(--surface-3)]" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-[var(--surface-2)]" />
            <div className="h-24 animate-pulse rounded-lg bg-[var(--surface-2)]" />
          </div>
        </div>
      ))}
    </div>
  );
}
