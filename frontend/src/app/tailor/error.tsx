"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-[var(--danger)] bg-[var(--danger-soft)] p-8 text-center"
    >
      <h2 className="text-lg font-semibold text-[var(--danger)]">CV Studio could not load</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-dim)]">{error.message}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-dim)]">
        Retry the page, or open Diagnostics if tailoring services keep failing.
      </p>
      <div className="mt-4 flex flex-col items-center justify-center gap-2 sm:flex-row">
        <Button onClick={reset} variant="outline" size="sm">
          Retry
        </Button>
        <Link
          href="/settings/system"
          className="inline-flex min-h-11 items-center rounded-[var(--radius-control)] px-3 text-sm font-semibold text-[var(--accent)] underline-offset-4 hover:underline sm:min-h-9"
        >
          Open Diagnostics
        </Link>
      </div>
    </div>
  );
}
