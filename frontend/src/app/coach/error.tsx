"use client"
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <p className="text-slate-500">Something went wrong loading this page.</p>
      <p className="text-xs text-slate-400">{error.message}</p>
      <button onClick={reset} className="rounded-lg border border-slate-200 px-4 py-2 text-sm hover:bg-slate-50">
        Try again
      </button>
    </div>
  )
}
