import { CheckCircle2, CircleAlert, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HostActions } from "@/components/setup/HostActions";
import type { SetupStatus } from "@/lib/setup";
import { modeLabel, profileLabel } from "@/lib/setup";

export function SetupStatusPanel({ status, loading, error, onCheckAgain }: {
  status: SetupStatus | null;
  loading: boolean;
  error: string | null;
  onCheckAgain: () => void;
}) {
  const ready = status?.overall_status === "ready";
  return (
    <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4" aria-labelledby="setup-status-title">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : ready ? <CheckCircle2 className="h-4 w-4 text-[var(--success)]" aria-hidden="true" /> : <CircleAlert className="h-4 w-4 text-[var(--warning)]" aria-hidden="true" />}
            <h2 className="font-semibold text-[var(--text)]" id="setup-status-title">Setup status</h2>
          </div>
          {status ? (
            <div className="mt-2 text-sm text-[var(--text-muted)]">
              <p>Selected: {modeLabel(status.intent.ai_mode)} · {profileLabel(status.intent.backend_profile)}</p>
              <p>Active: {profileLabel(status.capabilities.profile)} · {status.ai.healthy ? "ready" : status.ai.status.replaceAll("_", " ")}</p>
            </div>
          ) : <p className="mt-2 text-sm text-[var(--text-muted)]">Checking the local setup control plane.</p>}
          {error ? <p className="mt-2 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
        </div>
        <Button onClick={onCheckAgain} type="button" variant="outline">
          <RefreshCw className="h-4 w-4" aria-hidden="true" /> Check again
        </Button>
      </div>
      {status ? <HostActions actions={status.next_actions ?? []} /> : null}
    </section>
  );
}
