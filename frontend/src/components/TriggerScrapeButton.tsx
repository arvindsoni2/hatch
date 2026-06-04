"use client";

import { useState } from "react";
import { Zap, Loader2, CheckCircle2 } from "lucide-react";
import { API_BASE } from "@/lib/api";

export function TriggerScrapeButton({ variant = "primary" }: { variant?: "primary" | "link" }) {
  const [state, setState] = useState<"idle" | "running" | "started">("idle");

  const handleClick = async () => {
    setState("running");
    try {
      await fetch(`${API_BASE}/api/agents/scout/trigger`, { method: "POST" });
    } catch {
      // fire-and-forget — ignore network errors, scrape still runs on backend
    }
    setState("started");
  };

  if (variant === "link") {
    return (
      <span className="flex items-center gap-2">
        <button
          onClick={handleClick}
          disabled={state !== "idle"}
          className="text-xs font-medium underline underline-offset-2 disabled:opacity-50"
        >
          {state === "running" ? "Starting…" : state === "started" ? "Scrape started" : "Trigger scrape now"}
        </button>
        {state === "started" && (
          <span className="text-xs text-green-600 font-medium">
            ✓ Refresh Inbox in a few minutes to see new jobs
          </span>
        )}
      </span>
    );
  }

  return (
    <div className="space-y-3">
      <button
        onClick={handleClick}
        disabled={state !== "idle"}
        className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {state === "running" ? (
          <><Loader2 className="h-4 w-4 animate-spin" /> Starting…</>
        ) : (
          <><Zap className="h-4 w-4" /> Trigger scrape now</>
        )}
      </button>

      {state === "started" && (
        <div className="flex items-start gap-2 rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-800">
          <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-green-600" />
          <div>
            <span className="font-medium">Scrape started</span>
            <p className="mt-0.5 text-xs text-green-700">
              This runs in the background — it can take a couple of minutes. Refresh your Inbox when done.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
