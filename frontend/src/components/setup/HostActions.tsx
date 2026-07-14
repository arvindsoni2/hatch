"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import type { HostAction } from "@/lib/setup";

export function HostActions({ actions }: { actions: HostAction[] }) {
  const [copied, setCopied] = useState<string | null>(null);
  const commands = actions.filter((action) => action.command);
  if (commands.length === 0) return null;
  return (
    <section className="mt-4" aria-labelledby="host-actions-title">
      <h3 className="text-sm font-semibold text-[var(--text)]" id="host-actions-title">Host actions required</h3>
      <div className="mt-2 grid gap-2">
        {commands.map((action) => (
          <div className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3" key={action.id}>
            <p className="text-xs text-[var(--text-muted)]">{action.label}</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 overflow-x-auto text-xs text-[var(--text)]">{action.command}</code>
              <button aria-label={`Copy ${action.label} command`} className="rounded p-2 text-[var(--accent)]" onClick={async () => {
                await navigator.clipboard.writeText(action.command ?? "");
                setCopied(action.id);
              }} type="button">
                {copied === action.id ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
